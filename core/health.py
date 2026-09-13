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


def _check_disk(probe_dir: Path) -> ComponentHealth:
    import tempfile

    try:
        probe = Path(probe_dir) / "tradingagents_health_write_probe.tmp"
        probe.write_text("ok")
        probe.unlink()
        return ComponentHealth("disk", ComponentStatus.HEALTHY, "Write probe succeeded.")
    except OSError as exc:
        return ComponentHealth("disk", ComponentStatus.FAILED, f"Write probe failed: {exc}")


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


def _check_scheduler(db_paths: dict[str, Path]) -> ComponentHealth:
    path = db_paths.get("scheduler")
    if path is None or not Path(path).exists():
        return ComponentHealth("scheduler", ComponentStatus.UNKNOWN, "No scheduler_runs.db yet -- never run.")
    from scheduler.store import SchedulerRunStore

    store = SchedulerRunStore(path)
    try:
        active = store.active_lock()
    finally:
        store.close()
    if active is not None:
        return ComponentHealth(
            "scheduler", ComponentStatus.DEGRADED,
            f"Run in progress or possibly orphaned (run_id={active.run_id[:12]}, slot={active.slot_name!r}, started {active.started_at.isoformat()}).",
        )
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
