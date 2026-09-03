"""Phase 30 -- provider resilience: timeout, retry with exponential
backoff + jitter, a circuit breaker, an optional minimum-interval rate
limiter, and in-process call metrics -- wrapping ANY existing
`market.data_provider.MarketDataProvider` without modifying it.

Applied at the multi-symbol call sites this project's own Phase 29
operational audit named as the concrete gap: `scan`/`shadow-run`/
`evaluate`/`learn` all fetch one symbol's history per loop iteration,
sequentially, with no timeout/retry/backoff/rate-limit anywhere in that
loop today. A single hung or consistently-failing symbol could stall or
derail an entire watchlist run.

Timeout implementation note: a `concurrent.futures.ThreadPoolExecutor`
was deliberately NOT used here. Its worker threads are non-daemon, and
both its own context-manager `__exit__` (`shutdown(wait=True)`) and
Python's interpreter-shutdown atexit hook will BLOCK until a still-
running submitted call finishes -- so a genuinely hung network call
would make the *whole process* hang at exit even though `fetch_ohlcv`
itself had already "timed out" and returned an error. A plain
`daemon=True` thread has no such problem: the process can exit
immediately regardless of whether the abandoned call ever returns.
"""

import logging
import queue
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum

from market.data_provider import OHLCV, MarketDataError, MarketDataProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    """Mutable, in-process call statistics for ONE ResilientMarketDataProvider
    instance -- not persisted. A single CLI invocation's own visibility
    into what its provider layer did, not a cross-run audit trail
    (scheduler_runs.db already serves that role for scheduler-triggered
    runs; predictions/decisions/scanner/research stores serve it for
    the pipeline's own outputs)."""

    calls: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    circuit_rejections: int = 0
    total_latency_seconds: float = 0.0

    @property
    def success_rate(self) -> float | None:
        return (self.successes / self.calls) if self.calls > 0 else None

    @property
    def average_latency_seconds(self) -> float | None:
        return (self.total_latency_seconds / self.successes) if self.successes > 0 else None

    def summary_line(self) -> str:
        rate = f"{self.success_rate:.1%}" if self.success_rate is not None else "n/a"
        latency = f"{self.average_latency_seconds:.2f}s" if self.average_latency_seconds is not None else "n/a"
        return (
            f"calls={self.calls} successes={self.successes} failures={self.failures} "
            f"retries={self.retries} circuit_rejections={self.circuit_rejections} "
            f"success_rate={rate} avg_latency={latency}"
        )


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """After `failure_threshold` CONSECUTIVE failures, opens for
    `cooldown_seconds`: every request in that window is rejected
    WITHOUT attempting the network call at all -- the entire point is
    to stop hammering a genuinely unavailable provider rather than
    retrying every remaining symbol in a watchlist against a dead
    endpoint. After the cooldown, exactly one HALF_OPEN trial request is
    let through; its outcome decides whether the circuit re-closes or
    re-opens."""

    def __init__(self, *, failure_threshold: int = 5, cooldown_seconds: float = 60.0, clock_fn=time.monotonic):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock_fn = clock_fn
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        return self._state

    def allow_request(self) -> bool:
        if self._state != CircuitState.OPEN:
            return True
        if self._clock_fn() - self._opened_at >= self.cooldown_seconds:
            self._state = CircuitState.HALF_OPEN
            return True
        return False

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock_fn()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    backoff_factor: float = 2.0
    jitter_seconds: float = 0.25

    def delay_for_attempt(self, attempt: int, *, random_fn=random.random) -> float:
        """`attempt` is 1-indexed (the Nth failed attempt just made).
        Exponential backoff (base * factor**(attempt-1)) plus up to
        `jitter_seconds` of random jitter, specifically to avoid several
        symbols in one scan retrying in lockstep if they all failed at
        the same moment (a "thundering herd" against a recovering
        provider)."""
        backoff = self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))
        jitter = random_fn() * self.jitter_seconds
        return backoff + jitter


class ProviderCircuitOpenError(MarketDataError):
    """A MarketDataError subclass -- every EXISTING caller's `except
    MarketDataError` handling (market_intelligence.scanner's per-symbol
    exclusion, shadow-run's per-symbol FAILED, predictions.tracker's
    INSUFFICIENT_DATA path) already handles this correctly with zero
    changes to those call sites."""


def _call_with_timeout(fn, *args, timeout_seconds: float, **kwargs):
    """Runs `fn(*args, **kwargs)` on a daemon thread and waits up to
    `timeout_seconds` for it. On timeout, raises MarketDataError and
    returns immediately -- the abandoned thread is a daemon, so it can
    never block process exit (see module docstring)."""
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result_queue.put(("ok", fn(*args, **kwargs)))
        except Exception as exc:  # noqa: BLE001 -- must forward ANY exception to the caller thread, never swallow it
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    try:
        status, payload = result_queue.get(timeout=timeout_seconds)
    except queue.Empty:
        raise MarketDataError(f"Fetch exceeded the {timeout_seconds}s timeout.") from None
    if status == "error":
        raise payload
    return payload


class ResilientMarketDataProvider:
    """Wraps ANY MarketDataProvider with timeout + retry/backoff/jitter +
    a circuit breaker + an optional minimum-interval rate limiter +
    metrics. Every time-related dependency (sleep, clock) is injectable
    so unit tests never actually sleep for real unless they choose to."""

    def __init__(
        self, inner: MarketDataProvider, *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout_seconds: float = 15.0,
        min_interval_seconds: float = 0.0,
        metrics: ProviderMetrics | None = None,
        sleep_fn=time.sleep,
        clock_fn=time.monotonic,
    ):
        self._inner = inner
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(clock_fn=clock_fn)
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.metrics = metrics or ProviderMetrics()
        self._sleep_fn = sleep_fn
        self._clock_fn = clock_fn
        self._last_call_started_at: float | None = None

    def fetch_ohlcv(self, symbol: str, *, period: str = "1y", interval: str = "1d") -> OHLCV:
        if not self.circuit_breaker.allow_request():
            self.metrics.circuit_rejections += 1
            raise ProviderCircuitOpenError(
                f"Provider circuit breaker is OPEN (>= {self.circuit_breaker.failure_threshold} consecutive "
                f"failures) -- refusing to attempt {symbol!r} until the {self.circuit_breaker.cooldown_seconds}s "
                "cooldown elapses. This protects the rest of a multi-symbol run from hammering an unavailable provider."
            )

        last_error: Exception | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self._respect_rate_limit()
            self.metrics.calls += 1
            started_at = self._clock_fn()
            try:
                result = _call_with_timeout(self._inner.fetch_ohlcv, symbol, period=period, interval=interval, timeout_seconds=self.timeout_seconds)
            except MarketDataError as exc:
                last_error = exc
                self.metrics.failures += 1
                self.circuit_breaker.record_failure()
                if attempt < self.retry_policy.max_attempts:
                    self.metrics.retries += 1
                    delay = self.retry_policy.delay_for_attempt(attempt)
                    logger.info(
                        "Provider fetch for %s failed (attempt %d/%d): %s -- retrying in %.2fs",
                        symbol, attempt, self.retry_policy.max_attempts, exc, delay,
                    )
                    self._sleep_fn(delay)
                    continue
                break
            else:
                self.metrics.successes += 1
                self.metrics.total_latency_seconds += self._clock_fn() - started_at
                self.circuit_breaker.record_success()
                return result

        raise MarketDataError(
            f"Failed to fetch {symbol!r} after {self.retry_policy.max_attempts} attempt(s): {last_error}"
        ) from last_error

    def _respect_rate_limit(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        if self._last_call_started_at is not None:
            elapsed = self._clock_fn() - self._last_call_started_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep_fn(remaining)
        self._last_call_started_at = self._clock_fn()


def build_resilient_provider(
    inner: MarketDataProvider | None = None, *,
    max_attempts: int = 3,
    timeout_seconds: float = 15.0,
    min_interval_seconds: float = 0.0,
    circuit_failure_threshold: int = 5,
    circuit_cooldown_seconds: float = 60.0,
) -> ResilientMarketDataProvider:
    """Convenience factory matching `market.data_provider.
    get_market_data_provider`'s own default-construction pattern --
    `inner` defaults to the real Yahoo provider (deferred import, same
    discipline as everywhere else in this project)."""
    if inner is None:
        from market.data_provider import get_market_data_provider

        inner = get_market_data_provider()
    return ResilientMarketDataProvider(
        inner,
        retry_policy=RetryPolicy(max_attempts=max_attempts),
        circuit_breaker=CircuitBreaker(failure_threshold=circuit_failure_threshold, cooldown_seconds=circuit_cooldown_seconds),
        timeout_seconds=timeout_seconds,
        min_interval_seconds=min_interval_seconds,
    )
