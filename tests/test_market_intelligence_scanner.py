from datetime import datetime, timedelta

import pytest

from market.data_provider import OHLCV, MarketDataError, OHLCVBar
from market_data.universe import MarketUniverse
from market_intelligence.config import ScannerConfig
from market_intelligence.scanner import run_scan

_START = datetime(2023, 1, 2)


def _bars(
    closes: list[float], *, volumes: list[float] | None = None, high_mult: float = 1.01, low_mult: float = 0.99
) -> list[OHLCVBar]:
    volumes = volumes or [100_000.0] * len(closes)
    return [
        OHLCVBar(
            timestamp=_START + timedelta(days=i),
            open=close, high=close * high_mult, low=close * low_mult, close=close, volume=volumes[i],
        )
        for i, close in enumerate(closes)
    ]


def _ohlcv(
    symbol: str, closes: list[float], *, volumes: list[float] | None = None, high_mult: float = 1.01, low_mult: float = 0.99
) -> OHLCV:
    return OHLCV(symbol=symbol, interval="1d", bars=_bars(closes, volumes=volumes, high_mult=high_mult, low_mult=low_mult))


def _uptrend(n: int = 80, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + step * i for i in range(n)]


def _downtrend(n: int = 80, start: float = 200.0, step: float = 0.5) -> list[float]:
    return [start - step * i for i in range(n)]


def _flat(n: int = 80, value: float = 100.0) -> list[float]:
    return [value] * n


class _FakeProvider:
    """symbol -> OHLCV or Exception. Never touches the network."""

    def __init__(self, data: dict[str, OHLCV | Exception]):
        self._data = data
        self.calls: list[str] = []

    def fetch_ohlcv(self, symbol: str, *, period: str = "1y", interval: str = "1d") -> OHLCV:
        self.calls.append(symbol)
        outcome = self._data.get(symbol)
        if outcome is None:
            raise MarketDataError(f"no fixture data for {symbol}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _universe(*symbols: str) -> MarketUniverse:
    return MarketUniverse.from_watchlist(list(symbols))


# --- trend / momentum / breakout -----------------------------------------


def test_uptrend_symbol_scores_positive_trend_momentum_and_breakout():
    # A negligible high/low band (vs. the 1%-ish band used elsewhere in this
    # file) so a strictly-increasing close series also strictly increases
    # its own rolling high -- otherwise the prior bar's own high (close *
    # high_mult) can exceed today's close purely from the band, masking a
    # genuine new-high breakout.
    provider = _FakeProvider({"UP": _ohlcv("UP", _uptrend(), high_mult=1.0001, low_mult=0.9999)})
    report = run_scan(_universe("UP"), provider=provider, benchmark_symbol=None)

    assert len(report.candidates) == 1
    candidate = report.candidates[0]
    assert candidate.symbol == "UP"
    assert candidate.trend_score == 1.0
    assert candidate.momentum_score > 0
    assert candidate.breakout_score > 0
    assert candidate.composite_score > 0
    assert any("uptrend" in line for line in candidate.explanation)


def test_downtrend_symbol_scores_negative_trend_momentum_and_breakout():
    provider = _FakeProvider({"DOWN": _ohlcv("DOWN", _downtrend())})
    report = run_scan(_universe("DOWN"), provider=provider, benchmark_symbol=None)

    candidate = report.candidates[0]
    assert candidate.trend_score == -1.0
    assert candidate.momentum_score < 0
    assert candidate.breakout_score < 0
    assert candidate.composite_score < 0


def test_ranking_puts_the_stronger_uptrend_first():
    provider = _FakeProvider(
        {
            "STRONG": _ohlcv("STRONG", _uptrend(step=2.0)),
            "WEAK": _ohlcv("WEAK", _uptrend(step=0.1)),
        }
    )
    report = run_scan(_universe("STRONG", "WEAK"), provider=provider, benchmark_symbol=None)

    assert [c.symbol for c in report.candidates] == ["STRONG", "WEAK"]


# --- screening gates -------------------------------------------------------


def test_insufficient_history_is_excluded_not_scored():
    provider = _FakeProvider({"NEW": _ohlcv("NEW", _uptrend(n=10))})
    report = run_scan(_universe("NEW"), provider=provider, benchmark_symbol=None)

    assert report.candidates == []
    assert len(report.excluded) == 1
    assert "Insufficient history" in report.excluded[0].reason


def test_data_fetch_failure_is_excluded_with_reason_not_a_crash():
    provider = _FakeProvider({"BAD": MarketDataError("simulated outage")})
    report = run_scan(_universe("BAD"), provider=provider, benchmark_symbol=None)

    assert report.candidates == []
    assert "Data fetch failed" in report.excluded[0].reason


def test_one_bad_symbol_does_not_abort_the_scan_for_the_rest():
    provider = _FakeProvider(
        {"GOOD": _ohlcv("GOOD", _uptrend()), "BAD": MarketDataError("simulated outage")}
    )
    report = run_scan(_universe("GOOD", "BAD"), provider=provider, benchmark_symbol=None)

    assert [c.symbol for c in report.candidates] == ["GOOD"]
    assert [e.symbol for e in report.excluded] == ["BAD"]


def test_liquidity_gate_excludes_thin_volume():
    provider = _FakeProvider({"THIN": _ohlcv("THIN", _uptrend(), volumes=[1.0] * 80)})
    config = ScannerConfig(min_avg_daily_value=1_000_000.0)
    report = run_scan(_universe("THIN"), provider=provider, benchmark_symbol=None, config=config)

    assert report.candidates == []
    assert "Avg daily value" in report.excluded[0].reason


def test_price_gate_excludes_below_minimum():
    provider = _FakeProvider({"PENNY": _ohlcv("PENNY", _flat(value=1.0))})
    config = ScannerConfig(min_price=5.0)
    report = run_scan(_universe("PENNY"), provider=provider, benchmark_symbol=None, config=config)

    assert report.candidates == []
    assert "below minimum" in report.excluded[0].reason


def test_default_config_gates_are_no_ops():
    """No liquidity/price/volume study exists yet -- defaults must not
    silently reject anything an evidence-based threshold hasn't earned."""
    provider = _FakeProvider({"THIN": _ohlcv("THIN", _flat(value=1.0), volumes=[1.0] * 80)})
    report = run_scan(_universe("THIN"), provider=provider, benchmark_symbol=None)

    assert len(report.candidates) == 1


# --- relative strength / benchmark -----------------------------------------


def test_relative_strength_positive_when_symbol_outperforms_benchmark():
    provider = _FakeProvider(
        {
            "OUT": _ohlcv("OUT", _uptrend(step=1.0)),
            "^NSEI": _ohlcv("^NSEI", _flat()),
        }
    )
    report = run_scan(_universe("OUT"), provider=provider, benchmark_symbol="^NSEI")

    candidate = report.candidates[0]
    assert candidate.relative_strength_score is not None
    assert candidate.relative_strength_score > 0
    assert report.benchmark_unavailable_reason is None


def test_benchmark_fetch_failure_degrades_gracefully_not_a_crash():
    provider = _FakeProvider(
        {"SYM": _ohlcv("SYM", _uptrend()), "^NSEI": MarketDataError("no benchmark data")}
    )
    report = run_scan(_universe("SYM"), provider=provider, benchmark_symbol="^NSEI")

    assert report.benchmark_unavailable_reason is not None
    candidate = report.candidates[0]
    assert candidate.relative_strength_score is None
    assert any("not available" in line for line in candidate.explanation)


def test_benchmark_none_skips_relative_strength_entirely():
    provider = _FakeProvider({"SYM": _ohlcv("SYM", _uptrend())})
    report = run_scan(_universe("SYM"), provider=provider, benchmark_symbol=None)

    assert report.benchmark_symbol is None
    assert report.benchmark_unavailable_reason is None
    assert report.candidates[0].relative_strength_score is None


# --- sector strength ---------------------------------------------------------


def test_sector_strength_favors_the_outperforming_sector():
    provider = _FakeProvider(
        {
            "IT1": _ohlcv("IT1", _uptrend(step=2.0)),
            "IT2": _ohlcv("IT2", _uptrend(step=1.8)),
            "BANK1": _ohlcv("BANK1", _flat()),
            "BANK2": _ohlcv("BANK2", _downtrend(step=0.2)),
        }
    )
    sector_map = {"IT1": "IT", "IT2": "IT", "BANK1": "BANK", "BANK2": "BANK"}
    report = run_scan(
        _universe("IT1", "IT2", "BANK1", "BANK2"), provider=provider, benchmark_symbol=None, sector_map=sector_map
    )

    by_symbol = {c.symbol: c for c in report.candidates}
    assert by_symbol["IT1"].sector_strength_score > 0
    assert by_symbol["IT2"].sector_strength_score > 0
    assert by_symbol["BANK1"].sector_strength_score < 0
    assert by_symbol["BANK2"].sector_strength_score < 0


def test_sector_strength_is_none_when_no_sector_map_given():
    provider = _FakeProvider({"SYM": _ohlcv("SYM", _uptrend())})
    report = run_scan(_universe("SYM"), provider=provider, benchmark_symbol=None, sector_map=None)

    candidate = report.candidates[0]
    assert candidate.sector_strength_score is None
    assert any("not available" in line and "sector" in line.lower() for line in candidate.explanation)


def test_sector_strength_is_none_for_an_untagged_symbol():
    provider = _FakeProvider(
        {"TAGGED": _ohlcv("TAGGED", _uptrend()), "UNTAGGED": _ohlcv("UNTAGGED", _flat())}
    )
    report = run_scan(
        _universe("TAGGED", "UNTAGGED"), provider=provider, benchmark_symbol=None, sector_map={"TAGGED": "IT"}
    )

    by_symbol = {c.symbol: c for c in report.candidates}
    assert by_symbol["TAGGED"].sector_strength_score is not None
    assert by_symbol["UNTAGGED"].sector_strength_score is None


# --- reproducibility / determinism -----------------------------------------


def test_scan_is_deterministic_given_identical_inputs():
    provider = _FakeProvider(
        {
            "A": _ohlcv("A", _uptrend(step=1.2)),
            "B": _ohlcv("B", _downtrend(step=0.7)),
            "C": _ohlcv("C", _flat()),
        }
    )
    now = datetime(2024, 6, 1, 12, 0, 0)

    report1 = run_scan(_universe("A", "B", "C"), provider=provider, benchmark_symbol=None, now=now)
    report2 = run_scan(_universe("A", "B", "C"), provider=provider, benchmark_symbol=None, now=now)

    assert report1.candidates == report2.candidates
    assert report1.excluded == report2.excluded
    scores = [c.composite_score for c in report1.candidates]
    assert scores == sorted(scores, reverse=True)


def test_scan_report_records_universe_and_config_metadata():
    provider = _FakeProvider({"A": _ohlcv("A", _uptrend())})
    config = ScannerConfig(min_bars=60)
    report = run_scan(_universe("A"), provider=provider, benchmark_symbol=None, config=config)

    assert report.universe_mode == "watchlist"
    assert report.universe_size == 1
    assert report.config_version == config.version_id()
    assert report.scan_id


# --- config ------------------------------------------------------------------


def test_scanner_config_version_id_is_deterministic_and_change_sensitive():
    a = ScannerConfig()
    b = ScannerConfig()
    c = ScannerConfig(min_avg_daily_value=500.0)

    assert a.version_id() == b.version_id()
    assert a.version_id() != c.version_id()


def test_scan_raises_for_bad_symbols_argument_type():
    with pytest.raises(ValueError):
        MarketUniverse.from_watchlist([])
