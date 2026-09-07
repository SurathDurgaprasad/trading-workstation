"""LIVE SYSTEM HARDENING mission -- unit coverage for live/critic_gate.py,
the bridge that wires the deterministic critic into paper-live. Real
single-symbol run_scan()/compute_benchmark_context() calls against a
FAKE provider (no network) -- proves the actual wiring (scanner evidence
-> Decision -> critic.engine.evaluate()), not just mocked-out plumbing.
"""
from datetime import datetime, timedelta, timezone

import pytest

from live.critic_gate import CriticGate, DEFAULT_REFRESH_SECONDS
from market.data_provider import MarketDataError, OHLCV, OHLCVBar
from strategy.signal import ReasonCode, Side, Signal

_START = datetime(2023, 1, 2)


def _uptrend_bars(n: int = 250, start: float = 100.0, step: float = 1.0) -> list[OHLCVBar]:
    """Enough history (250 bars) to comfortably clear ScannerConfig's own
    min_bars=60 gate AND learning.regime.classify_regime_at's real
    BROAD_TREND_SMA_PERIOD=200 requirement -- a real UPTREND regime, not
    an UNKNOWN from insufficient warm-up."""
    bars = []
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=_START + timedelta(days=i), open=close, high=close * 1.01, low=close * 0.99,
            close=close, volume=1_000_000.0,
        ))
    return bars


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar], *, raise_error: bool = False):
        self._bars = bars
        self._raise_error = raise_error
        self.fetch_count = 0

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.fetch_count += 1
        if self._raise_error:
            raise MarketDataError(f"simulated fetch failure for {symbol}")
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


def _buy_signal(**overrides) -> Signal:
    base = dict(
        symbol="AAPL", generated_at=_START + timedelta(days=249), side=Side.LONG,
        reference_price=349.0, stop_price=340.0, target_price=370.0, risk_reward=2.0,
        strategy_name="trend_momentum_baseline", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def _gate(bars=None, *, raise_error=False, clock=None, **overrides) -> tuple[CriticGate, _FakeProvider]:
    provider = _FakeProvider(bars or _uptrend_bars(), raise_error=raise_error)
    gate = CriticGate(symbol="AAPL", provider=provider, benchmark_symbol=None, clock=clock or (lambda: 0.0), **overrides)
    return gate, provider


def _real_indicators(bars=None):
    """Real TechnicalIndicators computed from the SAME kind of bars the
    live pipeline's own latest_indicators() would produce -- a live-
    pipeline-sourced Decision always has these once bars have
    accumulated, so this reflects realistic usage (see live/pipeline.py's
    _handle_signal, which always calls latest_indicators() before the
    critic gate -- indicators=None is only the "not yet warmed up" edge
    case, covered separately)."""
    from market.data_provider import OHLCV
    from market.indicators import compute_indicators

    return compute_indicators(OHLCV(symbol="AAPL", interval="1d", bars=bars or _uptrend_bars()))


def test_a_real_buy_signal_with_real_supporting_evidence_is_approved():
    # The critic's own DATA_FRESHNESS/FUTURE_TIMESTAMP checks compare
    # market_context.as_of against a real "now" -- correct behavior for a
    # genuine live pipeline (whose indicators are always fresh), but this
    # fixture's synthetic bars are dated 2023 regardless of when the test
    # suite itself runs, so `now` must be pinned to that same synthetic
    # era (same fix shape as tests/test_shadow_run.py's own fixture).
    gate, _ = _gate()
    result = gate.evaluate(
        _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
        kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    assert result.blocked is False
    assert result.assessment is not None
    assert result.decision is not None
    assert result.decision.scanner_evidence is not None  # real, not fabricated
    assert result.decision.market_context is not None  # real, from the live indicator series
    assert result.decision.label.value == "BUY"


def test_missing_indicators_alone_is_insufficient_evidence_not_a_crash():
    """A live pipeline's very first bar for a symbol has no indicator
    history yet -- latest_indicators() can genuinely return None. With no
    market_context AND no research_evidence (never available in the live
    pipeline), the critic's own INSUFFICIENT_EVIDENCE verdict is the
    correct, honest outcome -- not a fabricated pass, not a crash."""
    gate, _ = _gate()
    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=False,
        existing_pending_order=False, existing_open_position=False,
    )
    assert result.blocked is True
    assert result.assessment.verdict.value == "INSUFFICIENT_EVIDENCE"


def test_kill_switch_active_blocks_via_the_real_critic_hard_check():
    gate, _ = _gate()
    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=True,
        existing_pending_order=False, existing_open_position=False,
    )
    assert result.blocked is True
    assert "Kill switch" in result.block_reason
    assert result.assessment.verdict.value == "REJECT"


def test_duplicate_exposure_blocks_via_the_real_critic_hard_check():
    gate, _ = _gate()
    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=False,
        existing_pending_order=False, existing_open_position=True,
    )
    assert result.blocked is True
    assert result.assessment.verdict.value == "REJECT"
    assert "DUPLICATE_EXPOSURE" in result.assessment.failed_checks


def test_a_provider_failure_fails_closed_not_open():
    """The critic must never silently pass a signal because evidence
    could not be fetched -- a data outage must block, not wave through."""
    gate, _ = _gate(raise_error=True)
    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=False,
        existing_pending_order=False, existing_open_position=False,
    )
    assert result.blocked is True
    assert result.assessment is None  # the critic never ran -- there was nothing real to evaluate
    assert "simulated fetch failure" in result.block_reason


def test_a_symbol_the_scanner_excludes_fails_closed():
    """Too little history -> the scanner excludes the symbol -> no
    CandidateScore exists -> fail closed, never a fabricated pass."""
    gate, _ = _gate(bars=_uptrend_bars(n=10))  # far below min_bars=60
    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=False,
        existing_pending_order=False, existing_open_position=False,
    )
    assert result.blocked is True
    assert result.assessment is None


def test_evidence_is_cached_within_the_refresh_window():
    """Scanner/benchmark evidence is a daily-timeframe signal -- refreshing
    it on every live tick would be wasted network calls, not extra safety.
    Two evaluate() calls within the refresh window must reuse one fetch."""
    gate, provider = _gate(clock=lambda: 100.0)
    gate.evaluate(_buy_signal(), indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False)
    first_fetch_count = provider.fetch_count
    assert first_fetch_count > 0

    gate.evaluate(_buy_signal(), indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False)
    assert provider.fetch_count == first_fetch_count  # no new fetch -- cache reused


def test_evidence_refreshes_after_the_configured_window_elapses():
    clock_value = [0.0]
    gate, provider = _gate(clock=lambda: clock_value[0], refresh_seconds=60.0)
    gate.evaluate(_buy_signal(), indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False)
    first_fetch_count = provider.fetch_count

    clock_value[0] = 61.0  # past the 60s refresh window
    gate.evaluate(_buy_signal(), indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False)
    assert provider.fetch_count > first_fetch_count


def test_default_refresh_seconds_is_fifteen_minutes():
    assert DEFAULT_REFRESH_SECONDS == 900.0
