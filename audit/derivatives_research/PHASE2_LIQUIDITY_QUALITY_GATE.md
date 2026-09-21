# Phase 2 — Liquidity / Data Quality Gate

Frozen **before** any predictive result is computed (this document is written immediately after
Phase 1's own data-availability findings, before Phase 3/4/5 touch any prediction target).

## Quantified finding carried forward from Phase 1

A real full-month sample (NIFTY ATM CALL, hourly, August 2025) found **0% zero-volume, 0% zero-OI,
0% null-IV** — the ATM-restricted rolling-option endpoint is, by construction, far more liquid than
the raw NSE bhavcopy full chain (85.8%/75.2% zero-volume in the prior pass's own measurement). **The
one real defect found**: the final 1-2 trading sessions before a contract's own expiry show BOTH
near-zero/degenerate IV (0.0, 0.4) AND implausible volume values (~1,000x every other bar in the
same series) — a genuine data-quality artifact in the raw feed, not a processing bug.

## Liquidity/quality rules — defined BEFORE looking at any predictive result

1. **IV plausibility floor**: exclude any bar with `iv < 3.0` (percent). NIFTY's own realized/
   implied volatility has not been credibly below 3% in this project's own already-verified India
   VIX history (the lowest multi-year India VIX readings are generally in the low-to-mid teens even
   in the calmest regimes) — a value below 3% is treated as a degenerate/artifact observation, not a
   genuine market IV reading. This threshold is set from general market-knowledge plausibility, NOT
   tuned against this research's own predictive results.
2. **Expiry-proximity exclusion**: exclude any bar dated within 2 calendar days of the OPTION'S OWN
   likely expiry. Since this endpoint does not return an absolute expiry date (Phase 1's own
   disclosed gap), this is operationalized via the `expiryFlag=WEEK` weekly-contract convention's
   own known Tuesday/Thursday-style weekly expiry pattern is NOT relied upon (too fragile, an
   unverified assumption) — instead, `expiryFlag=MONTH` is used throughout (matching Phase 1's own
   verification calls), and the exclusion is operationalized directly on the OBSERVED IV/volume
   degeneracy pattern itself: any bar whose OWN volume exceeds a 20x-of-trailing-10-bar-median
   ceiling is excluded as an implausible-volume artifact (a general, real, quantitative rule that
   directly targets the OBSERVED defect, not a calendar-based guess about which days are "close to
   expiry").
3. **Minimum valid strikes for skew**: a skew observation requires BOTH its ATM and ATM+1 (or ATM
   and ATM-1) leg to independently pass rules 1-2 at the SAME timestamp; if either leg fails, the
   whole skew observation for that timestamp is dropped, not partially computed.
4. **ATM proximity**: by construction — every feature in Phase 3 uses `ATM`, `ATM+1`, or `ATM-1`
   only (never a deep-OTM/ITM strike), which is itself the primary liquidity control, consistent
   with why the raw endpoint showed 0% zero-volume in the first place.
5. **Valid expiry selector**: only `expiryCode=1` (next) and `expiryCode=2` (far) are used —
   `expiryCode=0` is excluded entirely (a genuine API defect, not a liquidity choice).
6. **Bid/ask**: not applicable — this data source does not carry bid/ask at all (already disclosed
   in the prior pass's Phase 5 leakage audit for the bhavcopy route; the rolling-option endpoint
   also does not return bid/ask, only OHLC/IV/OI/volume/spot).

## Adequacy determination

**A sufficiently liquid historical sample exists — proceeding, not stopping.** The near-0%
zero-volume/zero-OI/null-IV rate for ATM-proximate strikes, combined with the narrow, well
-understood, and now-quantitatively-guarded expiry-proximity defect, means this data source clears
the mission's own bar for "a sufficiently liquid subset exists for a robust historical experiment."
No IV surface will be manufactured from illiquid observations — the rules above are exclusion rules
(drop bad data), never imputation or interpolation across a liquidity gap.

## What was explicitly NOT done

No threshold above (3.0% IV floor, 20x-median volume ceiling, ATM±1 strike range) was tuned against
any predictive-return result — none has been computed yet at the time this document is frozen. These
are plausibility/data-quality rules only, derived from the RAW DATA'S OWN observed defect pattern
(Phase 1's real, empirical findings), not from any outcome this research is trying to predict.
