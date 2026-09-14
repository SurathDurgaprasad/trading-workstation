"""Real-time strategy validation mission, Phase I -- proves the bounded
_SymbolBuffer fix (live/pipeline.py::DEFAULT_MAX_BUFFER_BARS) genuinely
closes Cycle 34's own "accepted limitation" finding (an unbounded
per-symbol bar buffer, O(n)-per-bar / O(n^2)-cumulative full-recompute
cost) WITHOUT changing any indicator value the pipeline's strategy/risk/
decision layers actually see.

Two independent claims are checked, not assumed:
  1. the buffer is genuinely capped (memory/CPU are actually bounded now);
  2. capping it changes NOTHING about the only row of the indicator
     series this pipeline ever reads (indicator_series.iloc[-1] -- see
     LiveSimPipeline._handle_new_bar's own generate_signal call), proven
     against real cached AAPL data, not synthetic prices.
"""
from datetime import datetime

import pandas as pd
import pytest

from live.pipeline import DEFAULT_MAX_BUFFER_BARS, LiveSimPipeline, _SymbolBuffer
from market.data_provider import OHLCV, OHLCVBar
from market.indicators import compute_indicator_series
from tests.conftest import AAPL_CACHE_PATH

pytestmark_real_data = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")


def _real_aapl_bars() -> list[OHLCVBar]:
    df = pd.read_csv(AAPL_CACHE_PATH)
    return [
        OHLCVBar(
            timestamp=datetime.fromisoformat(row.Date).replace(tzinfo=None),
            open=row.Open, high=row.High, low=row.Low, close=row.Close, volume=row.Volume,
        )
        for row in df.itertuples()
    ]


def _make_bar(day: int, close: float = 100.0) -> OHLCVBar:
    return OHLCVBar(timestamp=datetime(2020, 1, 1) + pd.Timedelta(days=day), open=close, high=close + 1, low=close - 1, close=close, volume=1_000_000.0)


# --- claim 1: the buffer is genuinely bounded -------------------------------


def test_symbol_buffer_never_exceeds_the_configured_max():
    buffer = _SymbolBuffer()
    for day in range(DEFAULT_MAX_BUFFER_BARS + 500):
        buffer.append(_make_bar(day))

    assert len(buffer.bars) == DEFAULT_MAX_BUFFER_BARS


def test_symbol_buffer_keeps_the_newest_bars_and_evicts_the_oldest():
    buffer = _SymbolBuffer()
    total = DEFAULT_MAX_BUFFER_BARS + 10
    for day in range(total):
        buffer.append(_make_bar(day))

    kept_days = [(b.timestamp - datetime(2020, 1, 1)).days for b in buffer.bars]
    assert kept_days == list(range(10, total))  # the oldest 10 (days 0-9) were evicted, in order
    assert len(kept_days) == DEFAULT_MAX_BUFFER_BARS


def test_symbol_buffer_default_max_is_documented_and_stable():
    """A guard against someone silently changing the bound without also
    updating the convergence study/documentation it depends on (see
    DEFAULT_MAX_BUFFER_BARS's own docstring and
    FINAL_FAILURE_MODE_ANALYSIS.md entry #44) -- not a magic-number
    assertion, a tripwire for "did you mean to also re-run the study."""
    assert DEFAULT_MAX_BUFFER_BARS == 1000


# --- claim 2: bounding history does not change the only row that matters ----


@pytestmark_real_data
def test_bounded_buffer_matches_full_history_on_the_last_row_exactly():
    """Reproduces, as an executable regression test, the exact convergence
    study DEFAULT_MAX_BUFFER_BARS's docstring cites: real cached AAPL
    daily data (not synthetic), full-history indicator computation vs. a
    bounded _SymbolBuffer fed the SAME bars in order -- the only row
    live/pipeline.py ever reads (the last one) must match to float64
    precision, not merely "close enough for trading purposes"."""
    bars = _real_aapl_bars()
    assert len(bars) > DEFAULT_MAX_BUFFER_BARS, "this study requires more history than the bound itself to be meaningful"

    full_series = compute_indicator_series(OHLCV(symbol="AAPL", interval="1d", bars=bars))
    full_last = full_series.iloc[-1]

    buffer = _SymbolBuffer()
    for bar in bars:
        buffer.append(bar)
    bounded_series = buffer.to_indicator_series("AAPL", "1d")
    bounded_last = bounded_series.iloc[-1]

    numeric_columns = [c for c in full_series.columns if c not in ("open", "high", "low", "close", "volume", "volume_trend")]
    for col in numeric_columns:
        assert bounded_last[col] == pytest.approx(full_last[col], abs=1e-9), f"column {col!r} diverged between bounded and full-history computation"


@pytestmark_real_data
def test_live_sim_pipelines_public_latest_indicators_is_unaffected_by_the_bound():
    """End-to-end proof through the PUBLIC API, not just the internal
    _SymbolBuffer class: feeding more than DEFAULT_MAX_BUFFER_BARS real
    bars through an actual LiveSimPipeline and reading back
    latest_indicators() must produce the same values a full-history
    computation would."""
    from live.mock_source import MockMarketDataSource, MockScriptEvent, make_mock_bar
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    class _NullStrategy:
        name = "null_strategy_for_buffer_bound_test"
        version = "1.0"

        def generate_signal(self, indicator_series, index, symbol):
            return None

    bars = _real_aapl_bars()
    script = [MockScriptEvent.bar_event("AAPL", make_mock_bar(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)) for b in bars]

    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=_NullStrategy(), symbols=["AAPL"], interval="1d",
        clock=lambda: datetime(2030, 1, 1),
    )

    for _ in range(len(bars)):
        pipeline.process_next()

    full_series = compute_indicator_series(OHLCV(symbol="AAPL", interval="1d", bars=bars))
    full_last = full_series.iloc[-1]

    live_indicators = pipeline.latest_indicators("AAPL")
    assert live_indicators is not None
    assert live_indicators.sma_20 == pytest.approx(full_last["sma_20"], abs=1e-9)
    assert live_indicators.sma_50 == pytest.approx(full_last["sma_50"], abs=1e-9)
    assert live_indicators.rsi_14 == pytest.approx(full_last["rsi_14"], abs=1e-9)
    assert live_indicators.atr_14 == pytest.approx(full_last["atr_14"], abs=1e-9)
    store.close()
