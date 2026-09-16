"""Final-product-hardening: one authoritative health model, consumed by
BOTH the CLI (`main.py`'s `health` command) and the dashboard (`/health`
route) -- the release-gate mission's own explicit requirement ("do not
create separate incompatible health implementations for CLI and
dashboard").

This does NOT replace `readiness-check` (main.py's own pre-flight
check, Phase 14) -- that command has its own established output format,
exit-code contract, and extensive existing test suite; rewriting it
would be exactly the kind of unjustified rewrite this hardening
campaign's own "zero unnecessary rewrites" principle argues against.
This module is genuinely NEW coverage: `PRAGMA integrity_check` across
all 12 stores (readiness-check checks only one), Ollama reachability
(readiness-check never checked this at all -- a real, disclosed gap
found by this same campaign's own configuration audit), and a single
overall system status a caller can act on programmatically.

Deliberately a pure function taking its inputs (`db_paths`) as an
explicit argument rather than resolving them itself -- this keeps the
module trivially testable (no real database files needed for most
tests) and avoids hardcoding a second, possibly-drifting copy of
main.py's/dashboard/intelligence.py's own path-resolution logic; each
caller passes its own already-resolved paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ComponentStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class OverallStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SAFE_STOP = "SAFE_STOP"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: ComponentStatus
    detail: str = ""


@dataclass(frozen=True)
class SystemHealth:
    overall: OverallStatus
    components: tuple[ComponentHealth, ...] = field(default_factory=tuple)

    def get(self, name: str) -> ComponentHealth | None:
        return next((c for c in self.components if c.name == name), None)


# name -> (module path, class name), lazily imported inside
# _check_database so importing this module carries no per-store cost.
_STORE_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("experiments", "experiments.store", "ExperimentStore"),
    ("decision_engine", "decision_engine.store", "DecisionStore"),
    ("live_state", "live.state_store", "LiveStateStore"),
    ("promotion_gate", "strategy.promotion_store", "PromotionGateStore"),
    ("experiment_registry", "strategy.experiment_store", "ExperimentRegistryStore"),
    ("paper", "paper.store", "PaperStore"),
    ("scheduler", "scheduler.store", "SchedulerRunStore"),
    ("predictions", "predictions.store", "PredictionStore"),
    ("direction_forecasts", "predictions.direction_forecast_store", "DirectionForecastStore"),
    ("research", "research.store", "ResearchStore"),
    ("scanner", "market_intelligence.store", "ScanHistoryStore"),
    ("regime", "market_intelligence.regime_store", "MarketRegimeStore"),
)


def _check_database(db_paths: dict[str, Path]) -> ComponentHealth:
    """Aggregates `PRAGMA integrity_check` across every store whose db
    path was supplied AND already exists on disk -- a store that has
    never been created yet is not a failure, it just has nothing to
    check (UNKNOWN would be misleading too; it is correctly absent from
    the finding entirely, same posture as `db_size_bytes` returning 0
    for a nonexistent file rather than raising)."""
    import importlib

    findings: list[str] = []
    checked_count = 0
    for name, module_path, class_name in _STORE_REGISTRY:
        path = db_paths.get(name)
        if path is None or not Path(path).exists():
            continue
        checked_count += 1
        try:
            module = importlib.import_module(module_path)
            store_cls = getattr(module, class_name)
            store = store_cls(path)
            try:
                result = store.integrity_check()
                if result != "ok":
                    findings.append(f"{name}: {result}")
            finally:
                store.close()
        except Exception as exc:  # noqa: BLE001 -- a health check must never itself crash the caller
            findings.append(f"{name}: could not check ({type(exc).__name__}: {exc})")

    if checked_count == 0:
        return ComponentHealth("database", ComponentStatus.UNKNOWN, "No store database files exist yet.")
    if findings:
        return ComponentHealth("database", ComponentStatus.FAILED, "; ".join(findings))
    return ComponentHealth("database", ComponentStatus.HEALTHY, f"{checked_count} store(s) checked (of {len(db_paths)} configured), all ok.")


_DISK_FREE_BYTES_DEGRADED = 500 * 1024 * 1024
"""Autonomous hardening cycle 6: below this much free space on the
volume holding the data directory, report DEGRADED -- entry #8 of
FINAL_FAILURE_MODE_ANALYSIS.md previously disclosed this as a real,
unaddressed gap ("no disk-space health check exists"; a full disk would
only ever surface as a raw OSError/sqlite3.OperationalError at the
point of write, with no advance warning anywhere). 500MB is deliberately
generous headroom for a local, single-operator SQLite-backed system
whose total data footprint is small -- this is a warning to act before
things break, not a claim that writes are about to fail."""

_DISK_FREE_BYTES_FAILED = 50 * 1024 * 1024
"""Below this, report FAILED -- disk is already a CRITICAL component
(see _derive_overall_status), so this correctly escalates overall
status to FAILED and blocks the startup gate, the same fail-closed
posture a genuine write failure already gets from the write-probe
check below."""


def _check_disk(probe_dir: Path) -> ComponentHealth:
    """15-symbol live-fleet validation mission, real defect found live:
    the probe filename used to be a single fixed name shared by every
    caller. With N `paper-live` worker processes (fleet-supervise) all
    starting within the same second and all running this SAME startup
    gate against the SAME probe_dir (PROJECT_ROOT), one process's
    probe.unlink() could delete another process's probe file between
    ITS OWN write_text() and unlink() calls -- a real TOCTOU race, not
    hypothetical: observed live as a genuine SAFE_STOP (`[WinError 2]
    The system cannot find the file specified`) for one worker in a
    10-symbol Phase C run, correctly triggering this project's own
    bounded-restart mechanism (which recovered it on retry) rather than
    corrupting anything -- but the race itself was a real, closeable
    defect, not something to just tolerate. Fixed by giving every
    caller its own uniquely-named probe file (PID + a random suffix),
    so concurrent callers never touch the same path."""
    import os
    import shutil
    import uuid

    try:
        probe = Path(probe_dir) / f"tradingagents_health_write_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return ComponentHealth("disk", ComponentStatus.FAILED, f"Write probe failed: {exc}")

    try:
        free_bytes = shutil.disk_usage(probe_dir).free
    except OSError as exc:  # noqa: BLE001 -- the write probe above already proved the path itself works; a disk_usage-specific failure here is a separate, non-fatal reporting gap, not a write failure
        return ComponentHealth("disk", ComponentStatus.HEALTHY, f"Write probe succeeded. Free-space check unavailable: {exc}")

    free_mb = free_bytes / (1024 * 1024)
    if free_bytes < _DISK_FREE_BYTES_FAILED:
        return ComponentHealth("disk", ComponentStatus.FAILED, f"Only {free_mb:.0f}MB free -- writes may fail imminently.")
    if free_bytes < _DISK_FREE_BYTES_DEGRADED:
        return ComponentHealth("disk", ComponentStatus.DEGRADED, f"Only {free_mb:.0f}MB free -- consider freeing space soon.")
    return ComponentHealth("disk", ComponentStatus.HEALTHY, f"Write probe succeeded. {free_mb:.0f}MB free.")


def _check_ollama() -> ComponentHealth:
    try:
        from llm.provider import check_ollama_availability

        check_ollama_availability()
        return ComponentHealth("ollama", ComponentStatus.HEALTHY, "Reachable, configured models present.")
    except Exception as exc:  # noqa: BLE001 -- Ollama is optional; never let its absence crash a health check
        return ComponentHealth("ollama", ComponentStatus.DEGRADED, f"Unavailable: {exc}")


def _check_dhan_credentials() -> ComponentHealth:
    try:
        from live.dhan.config import DhanCredentialsMissingError, load_dhan_credentials

        load_dhan_credentials()
        return ComponentHealth("dhan", ComponentStatus.HEALTHY, "Credentials configured (connectivity not tested).")
    except DhanCredentialsMissingError as exc:
        return ComponentHealth("dhan", ComponentStatus.DISABLED, str(exc))


def _check_kill_switch(db_paths: dict[str, Path]) -> ComponentHealth:
    path = db_paths.get("live_state")
    if path is None or not Path(path).exists():
        return ComponentHealth("kill_switch", ComponentStatus.UNKNOWN, "No live_state.db yet -- never armed.")
    from live.state_store import LiveStateStore

    store = LiveStateStore(path)
    try:
        active = store.is_kill_switch_active()
    finally:
        store.close()
    if active:
        return ComponentHealth("kill_switch", ComponentStatus.DEGRADED, "ACTIVE -- new paper orders are blocked until reset.")
    return ComponentHealth("kill_switch", ComponentStatus.HEALTHY, "Inactive.")


_SUSTAINED_FAILURE_THRESHOLD = 3
"""Autonomous hardening cycle 3: how many consecutive non-COMPLETED runs
(FAILED or RECLAIMED) for a single slot, with no COMPLETED run since,
before a sustained failure (e.g. a market-data provider outage lasting
across several ticks) is surfaced as DEGRADED here -- see
SchedulerRunStore.consecutive_failures_for_slot's docstring for why this
check exists at all. 3 is deliberately low: a single bad tick is normal
operation (provider hiccups happen and `schedule loop` already retries
the next tick on its own), but three in a row with zero intervening
success is a real, actionable pattern worth an operator's attention."""


def _check_scheduler(db_paths: dict[str, Path]) -> ComponentHealth:
    path = db_paths.get("scheduler")
    if path is None or not Path(path).exists():
        return ComponentHealth("scheduler", ComponentStatus.UNKNOWN, "No scheduler_runs.db yet -- never run.")
    from scheduler.store import SchedulerRunStore

    store = SchedulerRunStore(path)
    try:
        active = store.active_lock()
        if active is not None:
            return ComponentHealth(
                "scheduler", ComponentStatus.DEGRADED,
                f"Run in progress or possibly orphaned (run_id={active.run_id[:12]}, slot={active.slot_name!r}, started {active.started_at.isoformat()}).",
            )
        for slot_name in store.distinct_slot_names():
            streak = store.consecutive_failures_for_slot(slot_name)
            if streak >= _SUSTAINED_FAILURE_THRESHOLD:
                last_failure = store.last_failed_run_for_slot(slot_name)
                reason = f" -- {last_failure.error or last_failure.detail}" if last_failure else ""
                return ComponentHealth(
                    "scheduler", ComponentStatus.DEGRADED,
                    f"Slot {slot_name!r} has failed its last {streak} consecutive run(s) with no success since{reason}.",
                )
    finally:
        store.close()
    return ComponentHealth("scheduler", ComponentStatus.HEALTHY, "No active run lock.")


def _check_risk_config() -> ComponentHealth:
    try:
        from risk.config import RiskConfig

        RiskConfig()
        return ComponentHealth("risk", ComponentStatus.HEALTHY, "Config loads and validates.")
    except Exception as exc:  # noqa: BLE001 -- report, do not propagate, from a health check
        return ComponentHealth("risk", ComponentStatus.FAILED, f"{type(exc).__name__}: {exc}")


def collect_system_health(
    *,
    db_paths: dict[str, Path] | None = None,
    probe_dir: Path | None = None,
    check_ollama: bool = True,
) -> SystemHealth:
    """The one function both `main.py health` and the dashboard's
    `/health` route call. `db_paths` keys are the names in
    `_STORE_REGISTRY` plus `"live_state"`/`"scheduler"` for the
    kill-switch/scheduler checks (both already in that registry under
    the same names, so one dict covers everything) -- pass whatever
    subset of stores you have paths for; a missing key is treated as
    "not yet created," not a failure. `check_ollama=False` skips the
    one real network call this function can make (to localhost, not
    the public internet) -- e.g. for a caller that wants a fast,
    zero-I/O-beyond-disk check.

    Deliberately does NOT check Yahoo/Dhan live connectivity or model
    file presence beyond Ollama's own required-models check -- a real
    network call to an external market-data provider on every health
    check would be exactly the "recompute on every page load" antipattern
    dashboard/intelligence.py's own module docstring already warns
    against; use `readiness-check --deep` for that, deliberately opt-in.
    Memory-pressure monitoring is not implemented (no `psutil` or
    equivalent dependency exists in this project; disk-space and
    database-integrity are the two resource-safety checks judged
    worth a real dependency addition, memory was not -- this is an
    an honest, disclosed omission, not a silent gap)."""
    db_paths = db_paths or {}
    probe_dir = probe_dir or Path.cwd()

    components = [
        ComponentHealth("application", ComponentStatus.HEALTHY, "Running."),
        _check_database(db_paths),
        _check_disk(probe_dir),
        _check_dhan_credentials(),
        _check_kill_switch(db_paths),
        _check_scheduler(db_paths),
        _check_risk_config(),
    ]
    if check_ollama:
        components.append(_check_ollama())

    overall = _derive_overall_status(components)
    return SystemHealth(overall=overall, components=tuple(components))


def _derive_overall_status(components: list[ComponentHealth]) -> OverallStatus:
    """CRITICAL components (whose failure means the deterministic core
    itself cannot be trusted): application, database, disk, risk.
    OPTIONAL components (whose failure degrades a feature but never the
    core pipeline): dhan, ollama, scheduler. kill_switch's ACTIVE state
    is reported as its own component DEGRADED, but is exactly the one
    condition that maps to overall SAFE_STOP -- it is a deliberate
    safety halt, not a malfunction, and the mission's own vocabulary
    (HEALTHY/DEGRADED/SAFE_STOP/FAILED) reserves a distinct state for
    exactly this case rather than conflating it with a broken
    dependency."""
    critical_names = {"application", "database", "disk", "risk"}
    kill_switch = next((c for c in components if c.name == "kill_switch"), None)
    if kill_switch is not None and kill_switch.status == ComponentStatus.DEGRADED and "ACTIVE" in kill_switch.detail:
        return OverallStatus.SAFE_STOP
    if any(c.status == ComponentStatus.FAILED and c.name in critical_names for c in components):
        return OverallStatus.FAILED
    if any(c.status in (ComponentStatus.DEGRADED, ComponentStatus.FAILED) for c in components):
        return OverallStatus.DEGRADED
    return OverallStatus.HEALTHY
