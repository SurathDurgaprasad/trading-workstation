"""INDIAN NSE PREDICTION ENGINE mission, Phase 3: persistence for
market_intelligence.regime.MarketRegimeReport -- the "MarketSnapshot"
concept the mission asks for already exists as real, tested code
(MarketRegimeReport already carries as_of/scan_id/breadth/benchmark/
sector_strength/sector_index_regimes/india_vix); what was missing is
durability. Before this, build_market_regime_report() was only ever
called from the standalone `regime` CLI command and printed -- never
saved, so no decision made using it could later be reproduced or
audited against what the market actually looked like at decision time.

Same convention as market_intelligence/store.py (ScanHistoryStore):
stdlib sqlite3, one file, explicit transaction, write-once (a report is
never updated in place). MarketRegimeReport is a plain frozen dataclass,
not a pydantic BaseModel (unlike ScanReport), so this module hand-rolls
its own to_dict/from_dict pair instead of reusing model_dump_json --
deliberately NOT converting MarketRegimeReport to pydantic just to reuse
ScanHistoryStore's exact code, since that would touch a module with its
own existing tests and callers for no functional gain.

Keyed by scan_id -- the SAME id market_intelligence.store.ScanHistoryStore
already keys ScanReport by, so a MarketRegimeReport and the ScanReport it
was computed alongside can always be correlated by that shared id without
either model needing to reference the other.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from market_intelligence.regime import BenchmarkContext, IndiaVixContext, MarketBreadth, MarketRegimeReport, SectorStrength

_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_regime_reports (
    scan_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_regime_reports_as_of ON market_regime_reports(as_of);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_to_dict(report: MarketRegimeReport) -> dict:
    """asdict() alone handles every nested dataclass field correctly
    (breadth/benchmark/sector_strength/sector_index_regimes/india_vix are
    all dataclasses or containers of them) -- the only field needing
    explicit handling is `as_of` (a datetime, not JSON-native)."""
    data = asdict(report)
    data["as_of"] = report.as_of.isoformat()
    return data


def _report_from_dict(data: dict) -> MarketRegimeReport:
    return MarketRegimeReport(
        as_of=datetime.fromisoformat(data["as_of"]),
        scan_id=data["scan_id"],
        breadth=MarketBreadth(**data["breadth"]),
        benchmark=BenchmarkContext(**data["benchmark"]),
        sector_strength=tuple(SectorStrength(**s) for s in data["sector_strength"]),
        sector_index_regimes={k: BenchmarkContext(**v) for k, v in data.get("sector_index_regimes", {}).items()},
        india_vix=IndiaVixContext(**data["india_vix"]) if data.get("india_vix") is not None else None,
    )


class MarketRegimeStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self):
        self._conn.execute("BEGIN")
        try:
            yield
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def save_report(self, report: MarketRegimeReport) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO market_regime_reports (scan_id, as_of, data_json, created_at) VALUES (?,?,?,?)",
                (report.scan_id, report.as_of.isoformat(), json.dumps(_report_to_dict(report)), _now()),
            )

    def get_report(self, scan_id: str) -> MarketRegimeReport | None:
        row = self._conn.execute("SELECT data_json FROM market_regime_reports WHERE scan_id = ?", (scan_id,)).fetchone()
        return _report_from_dict(json.loads(row[0])) if row else None

    def latest_report(self) -> MarketRegimeReport | None:
        row = self._conn.execute("SELECT data_json FROM market_regime_reports ORDER BY as_of DESC LIMIT 1").fetchone()
        return _report_from_dict(json.loads(row[0])) if row else None

    def list_reports(self, limit: int = 50) -> list[MarketRegimeReport]:
        rows = self._conn.execute(
            "SELECT data_json FROM market_regime_reports ORDER BY as_of DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_report_from_dict(json.loads(r[0])) for r in rows]
