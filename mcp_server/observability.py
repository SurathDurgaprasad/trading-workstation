import functools
import logging
import time
import uuid

from core.events import log_event

logger = logging.getLogger("trading.mcp")


def observed_tool(tool_name: str):
    """Every MCP tool invocation is traceable: request_id, timestamp
    (implicit in the log line), tool, duration, success/failure, error
    category. Structured logging only (spec §29) — no database yet, but the
    shape here is exactly what a future trade-journal/audit table would read
    from, matching risk.contracts.SignalRecord's own "don't discard, log it"
    philosophy from Phase 4.5."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request_id = uuid.uuid4().hex[:12]
            start = time.perf_counter()
            log_event(
                "mcp_tool_requested",
                request_id=request_id,
                tool=tool_name,
                symbol=kwargs.get("symbol"),
                interval=kwargs.get("interval"),
            )
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                log_event(
                    "mcp_tool_failed",
                    request_id=request_id,
                    tool=tool_name,
                    duration_ms=round(duration_ms, 1),
                    error_category=type(exc).__name__,
                )
                raise
            duration_ms = (time.perf_counter() - start) * 1000
            log_event(
                "mcp_tool_succeeded",
                request_id=request_id,
                tool=tool_name,
                duration_ms=round(duration_ms, 1),
            )
            return result

        return wrapper

    return decorator
