"""Step 1 of the H_MEANREV_010 point-in-time replay (Path 1 of the user's
own capital-allocation mission, 2026-09-21): fetch a paced series of real
NSE F&O bhavcopy snapshots across the required 10-year window, resolve
each raw symbol through quant_research/security_identity_map.py, and
write a canonical-symbol eligibility timeline to disk.

Deliberately ANNUAL granularity (not daily/monthly): eligibility-list
revisions are periodic, infrequent events, and NSE's own infrastructure
showed real rate-limiting behavior under rapid requests during Phase A's
own investigation. 11 sequential, single-shot requests (paced 3s apart)
is respectful of that; a nearby-date fallback (+/-1..5 trading days)
handles the case where the exact anchor date is a weekend/holiday, which
is expected and NOT an error (see Phase A2's own documented finding of
NSE's own bhavcopy archive's normal date-existence behavior).

Never fabricates a snapshot for a date that could not be retrieved -- a
missing anchor date after exhausting the fallback window is logged and
skipped, not guessed.
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # audit/<family>/scripts/this_file.py -> repo root
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from quant_research.point_in_time_fno_universe import fetch_fno_bhavcopy, parse_futstk_underlyings
from quant_research.security_identity_map import fetchable_symbol_for

CACHE_DIR = REPO_ROOT / "audit" / "edge_feasibility" / "bhavcopy_cache"
OUT_PATH = REPO_ROOT / "audit" / "edge_feasibility" / "POINT_IN_TIME_SNAPSHOTS.csv"

ANCHOR_DATES = [date(y, 6, 15) for y in range(2016, 2026)] + [date(2026, 9, 18)]
FALLBACK_OFFSETS = [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5]  # calendar days, tried in this order
REQUEST_PACING_SECONDS = 3.0


def find_snapshot(anchor: date):
    for offset in FALLBACK_OFFSETS:
        candidate_date = anchor + timedelta(days=offset)
        bhavcopy = fetch_fno_bhavcopy(candidate_date, CACHE_DIR)
        if bhavcopy is not None:
            return candidate_date, bhavcopy
        time.sleep(REQUEST_PACING_SECONDS)
    return None, None


def main():
    print("=" * 100)
    print("Fetching point-in-time NSE F&O bhavcopy snapshots (paced, annual anchors)")
    print("=" * 100)

    rows = []
    for anchor in ANCHOR_DATES:
        actual_date, bhavcopy = find_snapshot(anchor)
        if bhavcopy is None:
            print(f"anchor={anchor}: FAILED to retrieve any nearby trading date -- SKIPPED, not fabricated.")
            continue
        snapshot = parse_futstk_underlyings(bhavcopy)
        n_raw = len(snapshot.symbols)

        resolved_count, excluded_count = 0, 0
        for raw_symbol in snapshot.symbols:
            canonical = fetchable_symbol_for(raw_symbol)
            if canonical is not None:
                resolved_count += 1
                rows.append({"anchor_date": anchor, "actual_snapshot_date": actual_date, "raw_symbol": raw_symbol, "canonical_symbol": canonical, "format": bhavcopy.format_name})
            else:
                excluded_count += 1
        print(
            f"anchor={anchor}: actual={actual_date} format={bhavcopy.format_name} "
            f"raw_symbols={n_raw} resolved={resolved_count} excluded_by_identity_map={excluded_count}"
        )
        time.sleep(REQUEST_PACING_SECONDS)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(df)} (snapshot, canonical_symbol) rows to {OUT_PATH}")
    print(f"Distinct snapshot dates retrieved: {df['actual_snapshot_date'].nunique()} / {len(ANCHOR_DATES)} anchors")
    print(f"Distinct canonical symbols across all snapshots: {df['canonical_symbol'].nunique()}")


if __name__ == "__main__":
    main()
