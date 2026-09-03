"""Phase 30 -- provider resilience. Every time-related dependency (sleep,
clock) is injected as a fake in these tests -- no real sleeping except
in the one test that specifically proves the daemon-thread timeout
mechanism works under genuine concurrency (test_timeout_*), which uses
a deliberately short, bounded real sleep."""

import time

import pytest

from market.data_provider import OHLCV, MarketDataError
from market_data.resilience import (
    CircuitBreaker,
    CircuitState,
    ProviderCircuitOpenError,
    ProviderMetrics,
    ResilientMarketDataProvider,
    RetryPolicy,
    build_resilient_provider,
)


class _FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingSleep:
    def __init__(self, clock: _FakeClock | None = None):
        self.calls: list[float] = []
        self._clock = clock

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._clock is not None:
            self._clock.advance(seconds)


def _ohlcv(symbol: str) -> OHLCV:
    return OHLCV(symbol=symbol, interval="1d", bars=[])


class _ScriptedProvider:
    """Returns/raises according to a per-call script; records every call."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls: list[str] = []

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.calls.append(symbol)
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# --- ProviderMetrics -----------------------------------------------------------


def test_metrics_start_at_zero_with_no_rate_or_latency():
    m = ProviderMetrics()
    assert m.success_rate is None
    assert m.average_latency_seconds is None
    assert "calls=0" in m.summary_line()


def test_metrics_compute_rate_and_latency():
    m = ProviderMetrics(calls=4, successes=3, failures=1, total_latency_seconds=1.5)
    assert m.success_rate == pytest.approx(0.75)
    assert m.average_latency_seconds == pytest.approx(0.5)


# --- CircuitBreaker --------------------------------------------------------------


def test_circuit_starts_closed_and_allows_requests():
    cb = CircuitBreaker(failure_threshold=3, clock_fn=_FakeClock())
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_circuit_opens_after_consecutive_failure_threshold():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60, clock_fn=clock)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_circuit_success_resets_the_failure_count():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=3, clock_fn=clock)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # only 2 consecutive since the reset


def test_circuit_moves_to_half_open_after_cooldown_and_recloses_on_success():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock_fn=clock)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False  # cooldown not elapsed

    clock.advance(31)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_half_open_failure_reopens_immediately():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock_fn=clock)
    cb.record_failure()
    clock.advance(31)
    cb.allow_request()  # -> HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


# --- RetryPolicy -----------------------------------------------------------------


def test_delay_for_attempt_grows_exponentially_before_jitter():
    policy = RetryPolicy(base_delay_seconds=1.0, backoff_factor=2.0, jitter_seconds=0.0)
    assert policy.delay_for_attempt(1) == pytest.approx(1.0)
    assert policy.delay_for_attempt(2) == pytest.approx(2.0)
    assert policy.delay_for_attempt(3) == pytest.approx(4.0)


def test_delay_for_attempt_adds_bounded_jitter():
    policy = RetryPolicy(base_delay_seconds=1.0, backoff_factor=2.0, jitter_seconds=0.5)
    delay = policy.delay_for_attempt(1, random_fn=lambda: 1.0)  # max jitter
    assert delay == pytest.approx(1.5)
    delay = policy.delay_for_attempt(1, random_fn=lambda: 0.0)  # min jitter
    assert delay == pytest.approx(1.0)


# --- ResilientMarketDataProvider: success / retry / exhaustion ------------------


def test_succeeds_immediately_with_no_retries():
    inner = _ScriptedProvider([_ohlcv("AAPL")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(inner, sleep_fn=sleep, clock_fn=clock)

    result = provider.fetch_ohlcv("AAPL")

    assert result.symbol == "AAPL"
    assert sleep.calls == []
    assert provider.metrics.calls == 1
    assert provider.metrics.successes == 1
    assert provider.metrics.retries == 0
    assert provider.circuit_breaker.state == CircuitState.CLOSED


def test_retries_after_a_transient_failure_then_succeeds():
    inner = _ScriptedProvider([MarketDataError("transient"), _ohlcv("AAPL")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(inner, retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=1.0, jitter_seconds=0.0), sleep_fn=sleep, clock_fn=clock)

    result = provider.fetch_ohlcv("AAPL")

    assert result.symbol == "AAPL"
    assert len(inner.calls) == 2
    assert provider.metrics.retries == 1
    assert provider.metrics.successes == 1
    assert sleep.calls == [pytest.approx(1.0)]


def test_exhausts_retries_and_raises_with_a_clear_message():
    inner = _ScriptedProvider([MarketDataError("down"), MarketDataError("down"), MarketDataError("down")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(inner, retry_policy=RetryPolicy(max_attempts=3, jitter_seconds=0.0), sleep_fn=sleep, clock_fn=clock)

    with pytest.raises(MarketDataError, match="after 3 attempt"):
        provider.fetch_ohlcv("AAPL")

    assert len(inner.calls) == 3
    assert provider.metrics.failures == 3
    assert provider.metrics.retries == 2  # sleeps between attempts 1->2 and 2->3, not after the final failure
    assert len(sleep.calls) == 2


def test_no_retry_when_max_attempts_is_one():
    inner = _ScriptedProvider([MarketDataError("down")])
    provider = ResilientMarketDataProvider(inner, retry_policy=RetryPolicy(max_attempts=1), sleep_fn=lambda s: (_ for _ in ()).throw(AssertionError("must not sleep")))
    with pytest.raises(MarketDataError):
        provider.fetch_ohlcv("AAPL")
    assert len(inner.calls) == 1


# --- ResilientMarketDataProvider: circuit breaker integration -------------------


def test_circuit_opens_across_multiple_symbols_and_short_circuits_the_next_one():
    """The circuit breaker is checked once at the START of each
    fetch_ohlcv call, not mid-retry-loop -- so symbol A (3 failed
    attempts) and symbol B (3 more) both run to completion even though
    the 5th failure (partway through symbol B) already crosses the
    threshold=5. What must NOT happen is a third symbol ever reaching
    the inner provider at all once the breaker is open."""
    inner = _ScriptedProvider([
        MarketDataError("down"), MarketDataError("down"), MarketDataError("down"),  # symbol A: 3 failures
        MarketDataError("down"), MarketDataError("down"), MarketDataError("down"),  # symbol B: 3 more (5th trips the breaker)
    ])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(
        inner, retry_policy=RetryPolicy(max_attempts=3, jitter_seconds=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, cooldown_seconds=60, clock_fn=clock),
        sleep_fn=sleep, clock_fn=clock,
    )

    with pytest.raises(MarketDataError):
        provider.fetch_ohlcv("SYMBOL_A")
    with pytest.raises(MarketDataError):
        provider.fetch_ohlcv("SYMBOL_B")

    assert provider.circuit_breaker.state == CircuitState.OPEN
    assert len(inner.calls) == 6  # 3 + 3, both symbols ran their full retry budget

    with pytest.raises(ProviderCircuitOpenError):
        provider.fetch_ohlcv("SYMBOL_C")

    assert len(inner.calls) == 6  # UNCHANGED -- symbol C never reached the inner provider at all
    assert provider.metrics.circuit_rejections == 1


def test_a_success_before_the_threshold_prevents_the_circuit_from_opening():
    inner = _ScriptedProvider([MarketDataError("down"), MarketDataError("down"), _ohlcv("AAPL")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(
        inner, retry_policy=RetryPolicy(max_attempts=3, jitter_seconds=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=3, clock_fn=clock),
        sleep_fn=sleep, clock_fn=clock,
    )
    provider.fetch_ohlcv("AAPL")  # 2 failures then a success -- resets the streak
    assert provider.circuit_breaker.state == CircuitState.CLOSED


# --- ResilientMarketDataProvider: rate limiting ----------------------------------


def test_rate_limiter_sleeps_when_calls_are_faster_than_the_minimum_interval():
    inner = _ScriptedProvider([_ohlcv("AAPL"), _ohlcv("MSFT")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(inner, min_interval_seconds=2.0, sleep_fn=sleep, clock_fn=clock)

    provider.fetch_ohlcv("AAPL")
    clock.advance(0.5)  # much less than the 2s minimum interval
    provider.fetch_ohlcv("MSFT")

    assert sleep.calls == [pytest.approx(1.5)]  # topped up to exactly the 2s minimum


def test_rate_limiter_does_not_sleep_when_calls_are_already_slow_enough():
    inner = _ScriptedProvider([_ohlcv("AAPL"), _ohlcv("MSFT")])
    clock = _FakeClock()
    sleep = _RecordingSleep(clock)
    provider = ResilientMarketDataProvider(inner, min_interval_seconds=1.0, sleep_fn=sleep, clock_fn=clock)

    provider.fetch_ohlcv("AAPL")
    clock.advance(5.0)
    provider.fetch_ohlcv("MSFT")

    assert sleep.calls == []


def test_rate_limiting_disabled_by_default():
    inner = _ScriptedProvider([_ohlcv("AAPL"), _ohlcv("MSFT")])
    sleep = _RecordingSleep()
    provider = ResilientMarketDataProvider(inner, sleep_fn=sleep, clock_fn=_FakeClock())
    provider.fetch_ohlcv("AAPL")
    provider.fetch_ohlcv("MSFT")
    assert sleep.calls == []


# --- Timeout: genuine concurrency, real (short, bounded) sleep -------------------


class _HangingProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        time.sleep(2.0)  # much longer than the test's timeout below
        return _ohlcv(symbol)  # pragma: no cover -- never reached within the timeout


def test_timeout_returns_promptly_without_waiting_for_a_hung_call():
    """Proves the daemon-thread timeout mechanism actually works: the
    inner provider sleeps for 2s, the timeout is 0.1s -- this test must
    complete in well under 2s, not 2s+."""
    provider = ResilientMarketDataProvider(
        _HangingProvider(), timeout_seconds=0.1,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    started = time.monotonic()
    with pytest.raises(MarketDataError, match="timeout"):
        provider.fetch_ohlcv("AAPL")
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"fetch_ohlcv blocked for {elapsed:.2f}s -- the timeout did not actually bound the wait"


def test_timeout_error_is_retried_like_any_other_failure():
    provider = ResilientMarketDataProvider(
        _HangingProvider(), timeout_seconds=0.05,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01, jitter_seconds=0.0),
    )
    with pytest.raises(MarketDataError):
        provider.fetch_ohlcv("AAPL")
    assert provider.metrics.failures == 2
    assert provider.metrics.retries == 1


# --- build_resilient_provider -----------------------------------------------------


def test_build_resilient_provider_wraps_the_explicit_inner():
    inner = _ScriptedProvider([_ohlcv("AAPL")])
    provider = build_resilient_provider(inner)
    assert isinstance(provider, ResilientMarketDataProvider)
    result = provider.fetch_ohlcv("AAPL")
    assert result.symbol == "AAPL"


def test_build_resilient_provider_defaults_to_the_real_yahoo_factory(monkeypatch):
    import market.data_provider as market_data_provider_module

    fake = _ScriptedProvider([_ohlcv("AAPL")])
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake)

    provider = build_resilient_provider()
    result = provider.fetch_ohlcv("AAPL")
    assert result.symbol == "AAPL"
