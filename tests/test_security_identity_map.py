"""Unit tests for quant_research/security_identity_map.py."""
from quant_research.security_identity_map import (
    IDENTITY_RECORDS,
    IdentityEventType,
    fetchable_symbol_for,
    resolve,
)


def test_resolve_unknown_symbol_returns_none():
    assert resolve("RELIANCE.NS") is None  # never investigated, never a false "safe" answer


def test_rename_resolves_to_successor():
    record = resolve("MCDOWELL-N.NS")
    assert record is not None
    assert record.event_type == IdentityEventType.RENAME
    assert record.successor_symbol == "UNITDSPR.NS"


def test_merger_survivor_resolves_to_successor():
    record = resolve("PVR.NS")
    assert record.event_type == IdentityEventType.MERGER_SURVIVOR
    assert record.successor_symbol == "PVRINOX.NS"


def test_merger_extinguished_has_no_successor():
    record = resolve("HDFC.NS")
    assert record.event_type == IdentityEventType.MERGER_EXTINGUISHED
    assert record.successor_symbol is None


def test_unresolved_has_no_successor_and_no_event_date():
    record = resolve("PEL.NS")
    assert record.event_type == IdentityEventType.UNRESOLVED
    assert record.successor_symbol is None
    assert record.event_date is None


def test_fetchable_symbol_for_unknown_symbol_passes_through_unchanged():
    # A symbol never investigated by this table is NOT claimed to be problem-free --
    # the caller's own normal fetch attempt decides its fate.
    assert fetchable_symbol_for("TCS.NS") == "TCS.NS"


def test_fetchable_symbol_for_rename_returns_successor():
    assert fetchable_symbol_for("AMARAJABAT.NS") == "ARE&M.NS"


def test_fetchable_symbol_for_merger_extinguished_returns_none():
    assert fetchable_symbol_for("IDFC.NS") is None


def test_fetchable_symbol_for_unresolved_returns_none():
    assert fetchable_symbol_for("GUJGASLTD.NS") is None


def test_every_rename_or_survivor_record_has_a_successor_symbol():
    for record in IDENTITY_RECORDS:
        if record.event_type in (IdentityEventType.RENAME, IdentityEventType.MERGER_SURVIVOR):
            assert record.successor_symbol is not None, f"{record.historical_symbol} claims a recoverable type but has no successor"


def test_every_extinguished_or_unresolved_record_has_no_successor_symbol():
    for record in IDENTITY_RECORDS:
        if record.event_type in (IdentityEventType.MERGER_EXTINGUISHED, IdentityEventType.UNRESOLVED):
            assert record.successor_symbol is None, f"{record.historical_symbol} claims non-recoverable but has a successor -- inconsistent"


def test_every_record_has_a_source_and_note():
    # Never a silent/unsourced entry -- matches this project's own no-fabrication discipline.
    for record in IDENTITY_RECORDS:
        assert record.source.strip()
        assert record.note.strip()


def test_records_cover_exactly_the_14_symbol_sample():
    covered = {r.historical_symbol for r in IDENTITY_RECORDS}
    expected = {
        "HDFC.NS", "MINDTREE.NS", "LTI.NS", "SRTRANSFIN.NS", "MCDOWELL-N.NS", "IDFC.NS", "PVR.NS",
        "TATAMOTORS.NS", "AMARAJABAT.NS", "GMRINFRA.NS", "GUJGASLTD.NS", "IBULHSGFIN.NS", "L&TFH.NS", "PEL.NS",
    }
    assert covered == expected


def test_recoverable_count_matches_disclosed_finding():
    recoverable = [r for r in IDENTITY_RECORDS if r.event_type in (IdentityEventType.RENAME, IdentityEventType.MERGER_SURVIVOR)]
    non_recoverable = [r for r in IDENTITY_RECORDS if r.event_type == IdentityEventType.MERGER_EXTINGUISHED]
    unresolved = [r for r in IDENTITY_RECORDS if r.event_type == IdentityEventType.UNRESOLVED]
    assert len(recoverable) == 8
    assert len(non_recoverable) == 3
    assert len(unresolved) == 3
