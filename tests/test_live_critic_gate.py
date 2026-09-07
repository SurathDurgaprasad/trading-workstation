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


class _SelectiveFailureProvider:
    """Succeeds for every symbol except those named in `fail_for`, which
    raise a bare RuntimeError -- deliberately NOT MarketDataError.
    market_intelligence.scanner._screen_symbol/_fetch_benchmark and
    market_intelligence.regime.compute_benchmark_context all narrowly
    catch MarketDataError/ValueError themselves and degrade gracefully
    (an excluded candidate, an UNKNOWN-flavored BenchmarkContext) rather
    than raising -- a real, reassuring finding from adversarial
    self-review, but it means a MarketDataError never actually reaches
    CriticGate's own try/except at all. A genuinely unexpected exception
    type is what's needed to exercise CriticGate's OWN fail-closed
    handling (its atomic-update and staleness-bound behavior) rather
    than the underlying functions' already-graceful degradation."""

    def __init__(self, bars: list[OHLCVBar], *, fail_for: frozenset[str] = frozenset()):
        self._bars = bars
        self._fail_for = fail_for
        self.fetch_count = 0
        self.fetched_symbols: list[str] = []

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.fetch_count += 1
        self.fetched_symbols.append(symbol)
        if symbol in self._fail_for:
            raise RuntimeError(f"simulated unexpected failure for {symbol}")
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


# --- adversarial self-review findings: atomic update + staleness bound ------


def test_a_benchmark_fetch_failure_does_not_leave_a_partially_updated_candidate():
    """Real gap found and fixed via self-review: a benchmark-symbol
    fetch failure (here, run_scan()'s own internal benchmark fetch --
    run_scan() calls that before screening the main symbol, so it never
    even reaches CriticGate's separate compute_benchmark_context() call
    in this exact scenario, though the same all-or-nothing guarantee
    covers either one raising) must not leave self._candidate set from
    a partial/inconsistent state. Both real fetches must succeed
    together, or neither cached field changes -- fail closed, not a
    partial pass."""
    provider = _SelectiveFailureProvider(_uptrend_bars(), fail_for=frozenset({"^NSEI"}))
    gate = CriticGate(symbol="AAPL", provider=provider, benchmark_symbol="^NSEI", clock=lambda: 0.0)

    result = gate.evaluate(
        _buy_signal(), indicators=None, kill_switch_active=False,
        existing_pending_order=False, existing_open_position=False,
    )

    # The failed refresh must be fail-closed -- no partial candidate silently accepted.
    assert result.blocked is True
    assert result.assessment is None


def test_a_transient_failure_does_not_block_forever_once_a_later_refresh_succeeds():
    """Companion to the atomic-update test: once a refresh genuinely
    succeeds (both real fetches), the gate must recover normally -- the
    earlier failure must not leave any lingering inconsistent state."""
    clock_value = [0.0]
    provider = _SelectiveFailureProvider(_uptrend_bars(), fail_for=frozenset({"^NSEI"}))
    gate = CriticGate(symbol="AAPL", provider=provider, benchmark_symbol="^NSEI", refresh_seconds=60.0, clock=lambda: clock_value[0])

    first = gate.evaluate(_buy_signal(), indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False)
    assert first.blocked is True  # benchmark fetch failed

    provider._fail_for = frozenset()  # simulate the transient issue clearing
    clock_value[0] = 61.0  # past the refresh window -- triggers a fresh attempt
    second = gate.evaluate(
        _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
        kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    assert second.blocked is False
    assert second.decision.scanner_evidence is not None


def test_evidence_is_treated_as_stale_after_max_staleness_seconds_of_repeated_failure():
    """Real gap found and fixed via self-review: _refresh_if_needed()'s
    own retry timer advances on every attempt, success or failure --
    without a separate staleness bound, cached evidence from before a
    persistent outage began would be used forever. Once
    max_staleness_seconds has elapsed since the LAST successful refresh,
    the gate must fail closed even though self._candidate is still
    technically set from a long-ago success. Uses _SelectiveFailureProvider
    (RuntimeError, not MarketDataError) so the failure genuinely reaches
    CriticGate's own exception handling instead of being absorbed as a
    plain scanner exclusion -- see that class's own docstring."""
    clock_value = [0.0]
    provider = _SelectiveFailureProvider(_uptrend_bars(), fail_for=frozenset())
    gate = CriticGate(symbol="AAPL", provider=provider, benchmark_symbol=None, refresh_seconds=10.0, max_staleness_seconds=30.0, clock=lambda: clock_value[0])

    first = gate.evaluate(
        _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
        kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    assert first.blocked is False  # a real, successful first refresh

    provider._fail_for = frozenset({"AAPL"})
    for elapsed in (11.0, 22.0, 33.0):  # repeated refresh attempts, all now failing
        clock_value[0] = elapsed
        result = gate.evaluate(
            _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
            kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
        )

    # 33s since the LAST SUCCESSFUL refresh (at t=0) exceeds max_staleness_seconds=30s.
    assert result.blocked is True
    assert "stale" in result.block_reason.lower()


def test_evidence_stays_usable_within_the_staleness_window_despite_a_single_failed_retry():
    """The staleness bound must not be so aggressive that one failed
    retry immediately blocks -- only genuinely prolonged unavailability
    should."""
    clock_value = [0.0]
    provider = _SelectiveFailureProvider(_uptrend_bars(), fail_for=frozenset())
    gate = CriticGate(symbol="AAPL", provider=provider, benchmark_symbol=None, refresh_seconds=10.0, max_staleness_seconds=100.0, clock=lambda: clock_value[0])

    first = gate.evaluate(
        _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
        kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    assert first.blocked is False

    provider._fail_for = frozenset({"AAPL"})
    clock_value[0] = 11.0  # one failed retry, well within the 100s staleness bound
    second = gate.evaluate(
        _buy_signal(), indicators=_real_indicators(), now=_START + timedelta(days=249, hours=1),
        kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    assert second.blocked is False  # still using the good evidence from t=0
