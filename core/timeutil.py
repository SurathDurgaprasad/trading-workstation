"""Repository-wide datetime normalization policy.

This project's own bug history (three separate, independently-diagnosed
incidents, in Phase 33, Phase 37, and Phase 42) is one bug CLASS, not
three: comparing/sorting a naive `datetime` against a timezone-aware one
raises `TypeError: can't compare offset-naive and offset-aware
datetimes`, and every one of those incidents was a different call site
independently reinventing the same one- or two-line fix. Before this
module existed, at least four files each defined their own private
`_naive`/`_naive_utc`/`_normalize_for_sort`/`_to_timestamp` helper with
IDENTICAL logic (`predictions/tracker.py` had two DIFFERENT
implementations in the same file), and `main.py` inlined the same
pattern a fifth time. None of that duplication was a functional bug on
its own -- each individual copy was correct for its own call site -- but
it is exactly the condition that let the same bug class recur three
times: there was no single, discoverable, tested place to look.

THE POLICY (two genuinely different cases, not one):

1. Market/bar data (`to_naive`): this project's own real-world data is a
   genuine mix -- Yahoo/mock OHLCV bars are naive by convention
   (representing local exchange wall-clock time), real Dhan bars have
   been UTC-aware since the Phase 16 real-connectivity work. The
   established, tested, and STILL-CORRECT project convention for market
   data specifically is to normalize to NAIVE (never invent a timezone
   for the bar data itself, just strip an existing one so comparisons
   within a single series are consistent). Use `to_naive()` for market
   bar timestamps, index values, and anything compared against them
   (signal timestamps, entry times, "as of" cutoffs against a bar
   series).

2. Record/system metadata (`as_utc_aware`): predictions, decisions, and
   experiment records are created with `datetime.now(timezone.utc)` in
   practice, but a caller-constructed or older/test-fixture value might
   arrive naive. Use `as_utc_aware()` when comparing or sorting these
   record-level timestamps (never bar data) -- normalizing to
   UTC-AWARE, the opposite direction from case 1, because unlike bar
   data these records have no real ambiguity about their own timezone:
   they were always meant to be UTC, a bare value just means "someone
   forgot to attach tzinfo."

3. Matching an external scalar against a DataFrame index whose own
   awareness is not known in advance (`match_index_awareness`): the
   general form of `learning/regime.py`'s own Phase 33 fix -- adapt the
   SCALAR to whatever the series already is, in either direction, never
   the reverse (never invent or discard the series' own real timezone
   information).

Do not invent a fourth pattern for a new call site -- if none of the
three above fits, that itself is worth a comment explaining why, the
same way this module's own existence should now make the first two
patterns unnecessary to rediscover.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def to_naive(value: datetime | pd.Timestamp | str) -> datetime:
    """Market/bar-data convention (see module docstring, case 1): returns
    a naive `datetime`, stripping tzinfo if present, never inventing a
    timezone. Accepts anything `pd.Timestamp(value)` can parse (a real
    `datetime`, a `pd.Timestamp`, or a parseable string) so this can
    replace every one of the historical call sites regardless of which
    of those input shapes they individually handled."""
    parsed = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def as_utc_aware(value: datetime) -> datetime:
    """Record/system-metadata convention (see module docstring, case 2):
    returns a UTC-aware `datetime`, attaching `timezone.utc` ONLY if
    `value` arrived naive -- never re-converts an already-aware value
    (a value aware in a different zone keeps its own real offset, it is
    not coerced to UTC)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def match_index_awareness(value: datetime, index: pd.Index) -> datetime:
    """General form of `learning/regime.py`'s own Phase 33 fix (see
    module docstring, case 3): adapts `value` to whatever `index`'s own
    awareness already is, in either direction -- never touches `index`
    itself, never invents a timezone for the underlying data."""
    index_is_aware = getattr(index, "tz", None) is not None
    if index_is_aware and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    if not index_is_aware and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value
