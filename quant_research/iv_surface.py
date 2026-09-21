"""Phase 3 of the options-volatility-surface research pass (2026-09-21):
the smallest deterministic feature layer for ATM implied-volatility level
and put/call IV skew, built only after Phase 1 (data availability) and
Phase 2 (liquidity/quality gate,
`audit/derivatives_research/PHASE2_LIQUIDITY_QUALITY_GATE.md`) established
that a sufficiently liquid historical sample exists via Dhan's
`/charts/rollingoption` endpoint, with exactly one disclosed, quantified
data-quality defect (near-expiry IV/volume degeneracy) that this module
guards against.

Two features only, per the mission's own "do not combine into a complex
model initially" instruction and its own two-candidate scoping (ATM IV
level as primary, put/call skew as the one pre-declared backup — see
Phase 3's own companion document for the full rationale). Strike-relative
skew (ATM+1 vs ATM-1) and expiry term structure were deliberately NOT
built here, to avoid the "test dozens of variants" pattern the mission
explicitly prohibits.

No trading signal is computed anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

MIN_PLAUSIBLE_IV_PCT = 3.0
"""Below this, an IV reading is treated as a degenerate/artifact
observation, not a genuine market reading -- set from general market
-plausibility (NIFTY/India VIX has not credibly traded below this level
in this project's own already-verified multi-year history), NEVER tuned
against this research's own predictive result (Phase 2's own frozen
rule, unchanged here)."""

VOLUME_MEDIAN_WINDOW = 10
VOLUME_MEDIAN_MULTIPLE = 20.0
"""A bar whose own volume exceeds VOLUME_MEDIAN_MULTIPLE x the trailing
VOLUME_MEDIAN_WINDOW-bar median volume is flagged as an artifact -- the
exact, quantitative operationalization of the real defect Phase 1 found
(two near-expiry bars with ~1,000x every other bar's own volume). Uses
ONLY prior bars' own volumes (a trailing, causal median) -- never a
centered or forward-looking window, so no future information can affect
whether a PAST bar is flagged."""


@dataclass(frozen=True)
class OptionRollingBar:
    """One bar from Dhan's `/charts/rollingoption` response, already
    normalized: `timestamp` is the bar's own exchange-local (IST) time
    (Phase 1's own verified semantics); `strike` and `option_type` are
    read directly from the response's own per-bar arrays (never assumed
    constant across a request); `iv` is UNITS OF PERCENT (e.g. 9.36 means
    9.36%, matching Dhan's own raw response convention, not a 0-1
    fraction) -- no normalization applied here, callers must not assume
    a 0-1 scale."""

    timestamp: datetime
    strike: float
    option_type: str  # "CE" | "PE"
    iv: float
    oi: int
    volume: int
    spot: float
    close: float


def is_plausible_iv(iv: float) -> bool:
    return iv >= MIN_PLAUSIBLE_IV_PCT


def flag_volume_artifacts(bars: list[OptionRollingBar]) -> list[bool]:
    """Returns one bool per bar (same order as `bars`, which MUST already
    be sorted by timestamp -- not sorted here, since sorting is the
    caller's own well-defined responsibility and silently re-sorting
    would risk masking an out-of-order-data bug instead of surfacing it).
    `True` means "flagged as a volume artifact, exclude this bar." The
    first `VOLUME_MEDIAN_WINDOW` bars can never be flagged (insufficient
    trailing history) -- never fabricated as flagged OR clean, simply
    not evaluated by this rule (a separate, earlier-in-the-pipeline
    concern for whoever consumes a very short series)."""
    flags: list[bool] = []
    for i, bar in enumerate(bars):
        if i < VOLUME_MEDIAN_WINDOW:
            flags.append(False)
            continue
        trailing = sorted(b.volume for b in bars[i - VOLUME_MEDIAN_WINDOW:i])
        median = trailing[len(trailing) // 2]
        flags.append(median > 0 and bar.volume > VOLUME_MEDIAN_MULTIPLE * median)
    return flags


def compute_atm_iv_level(bars: list[OptionRollingBar]) -> pd.Series:
    """ATM implied-volatility LEVEL feature.

    Timestamp: each bar's own `timestamp`, unchanged -- the feature at
    time t uses ONLY bar t's own IV, never a later bar's.
    Expiry selection: whatever `expiryCode` the caller's own fetch used
    to build `bars` (this function is agnostic to which one -- the
    caller's own fetch call, not this function, fixes it; the research
    script uses `expiryCode=1`, "next expiry," since `expiryCode=0` is a
    confirmed-broken Dhan endpoint value -- Phase 1's own finding).
    Strike selection: whatever `strike` selector the caller's own fetch
    used (the research script uses `"ATM"`).
    Interpolation: NONE -- a bar failing the quality gate is DROPPED
    from the output series, never interpolated or filled.
    Missing strikes: not applicable to this single-strike feature.
    Zero-volume contracts: excluded via `flag_volume_artifacts` (Phase
    1's own real, quantified defect pattern -- the endpoint itself
    showed 0% genuinely zero-volume bars in the sample checked; the
    guard exists for the DIFFERENT problem of implausibly INFLATED
    volume near expiry, not zero volume, which this data source does not
    actually exhibit).
    Stale observations: an IV reading below `MIN_PLAUSIBLE_IV_PCT` is
    dropped (Phase 1's own real, quantified near-expiry degeneracy).
    Units: percent (Dhan's own raw convention, e.g. 9.36 = 9.36%), NOT
    re-scaled.
    Normalization: none applied by this function -- any research script
    consuming this series decides its own normalization (e.g. dividing
    by a trailing mean), which is a MODELING choice, not a DATA choice,
    and therefore out of this module's own scope."""
    volume_flags = flag_volume_artifacts(bars)
    rows = [
        (bar.timestamp, bar.iv)
        for bar, flagged in zip(bars, volume_flags)
        if is_plausible_iv(bar.iv) and not flagged
    ]
    if not rows:
        return pd.Series(dtype=float)
    index, values = zip(*rows)
    return pd.Series(values, index=pd.DatetimeIndex(index), name="atm_iv_level").sort_index()


def compute_put_call_iv_skew(call_bars: list[OptionRollingBar], put_bars: list[OptionRollingBar]) -> pd.Series:
    """PUT/CALL IV ASYMMETRY feature: `put_iv - call_iv` at matching
    timestamps.

    Timestamp: the SAME timestamp must appear in both `call_bars` and
    `put_bars` for an observation to exist -- an exact match, no nearest
    -neighbor tolerance (a call/put pair observed at slightly different
    times would not be a genuine same-moment comparison).
    Expiry/strike selection: same as `compute_atm_iv_level` -- caller
    -controlled via which bars are passed in; the research script uses
    the SAME `"ATM"` strike and `expiryCode=1` for both legs, confirmed
    in Phase 1 to return the SAME strike value for both option types at
    a matching timestamp.
    Interpolation: NONE.
    Missing strikes: a timestamp present in only one of the two inputs
    (e.g. the call leg passed the quality gate but the put leg did not)
    produces NO skew observation for that timestamp -- never a
    single-leg approximation.
    Zero-volume / stale observations: each leg is independently passed
    through `is_plausible_iv` + `flag_volume_artifacts` BEFORE matching
    -- a degenerate reading on either leg excludes that timestamp
    entirely, not just the affected leg.
    Units: percentage points (a direct subtraction of two percent
    -unit IV readings).
    Normalization: none applied here, matching `compute_atm_iv_level`."""
    call_clean = _clean_bars(call_bars)
    put_clean = _clean_bars(put_bars)
    call_by_ts = {bar.timestamp: bar.iv for bar in call_clean}
    put_by_ts = {bar.timestamp: bar.iv for bar in put_clean}
    common = sorted(set(call_by_ts) & set(put_by_ts))
    if not common:
        return pd.Series(dtype=float)
    values = [put_by_ts[ts] - call_by_ts[ts] for ts in common]
    return pd.Series(values, index=pd.DatetimeIndex(common), name="put_call_iv_skew")


def _clean_bars(bars: list[OptionRollingBar]) -> list[OptionRollingBar]:
    volume_flags = flag_volume_artifacts(bars)
    return [bar for bar, flagged in zip(bars, volume_flags) if is_plausible_iv(bar.iv) and not flagged]
