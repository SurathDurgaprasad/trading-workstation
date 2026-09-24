# Research results — index

A concise index of every research program this project ran. **69 hypotheses tested, 0
promoted.** See [`RESEARCH_METHODOLOGY.md`](RESEARCH_METHODOLOGY.md) for how, and
[`EDGE_DISCOVERY_FINAL_REPORT.md`](EDGE_DISCOVERY_FINAL_REPORT.md) for the terminal,
full-history conclusion. The full, per-hypothesis evidence lives in
`strategy/hypothesis_registry.py` and the individual reports linked below — this page
does not restate their evidence in detail, only their outcome and where to find it.

| Program | Question | Data | Conclusion | Report | Status |
|---|---|---|---|---|---|
| **OHLCV baseline (entry/exit)** | Does the `TrendMomentumBaseline` strategy, or any variant of it (5 entry filters, 5 exit rules), have a demonstrable edge? | 41-symbol (32 NSE + 9 US), 5y daily backtest; corroborated live 2026-09-21 | REJECTED — underperforms buy-and-hold and 96% of random-entry Monte Carlo iterations; live confirms (4.7% win rate vs. ~33% breakeven) | [`RESEARCH_FOUNDATION_FINAL_OUTPUT.md`](RESEARCH_FOUNDATION_FINAL_OUTPUT.md), [`SCIENTIFIC_FINAL_REPORT.md`](SCIENTIFIC_FINAL_REPORT.md) | CLOSED, standing-prohibited from further tuning |
| **Mean reversion** | Does an oversold/relative-weakness z-score signal, at any of 14 tested refinements (regime-gating, mechanism decomposition, execution structure, sizing, point-in-time universe correction), produce a tradable edge? | 32–208 symbol NSE/US universes, 5–10y daily | REJECTED at the portfolio-realism stage even where a raw signal survived point-in-time correction (`H_MEANREV_014`) | `H_MEANREV_*` entries in `strategy/hypothesis_registry.py`; `audit/edge_feasibility/PATH1_MEAN_REVERSION_POINT_IN_TIME_CLOSURE.md` | CLOSED, standing-prohibited from further variants |
| **Breakout / relative strength / momentum-acceleration** | Does "buying strength" (breakout, relative strength, momentum acceleration, post-shock strength) predict continuation? | Same universes as above | REJECTED across 5+ independently-designed tests — repeatedly underperforms or reverses | `H_RELSTRENGTH_001`, `H_BREAKOUT_001`, `H_VOL_001`, `H_EXTREME_001`, `H_MOMENTUM_001` | CLOSED (exhausted direction, not formally prohibited) |
| **Cross-sectional laggard reversal** | Does a bottom-quintile, 60-day-lookback ranking predict a 20-day reversal? | 32-symbol NSE universe, 10y daily | Raw measurement is the strongest single finding in the project's history (survives cost, era-stable) — but every executable design (ATR stop/target) fails, and universe-widening reverses the raw effect | `H_XSECT_001`–`H_XSECT_006` | Raw finding open/INCONCLUSIVE; every execution attempt CLOSED |
| **Market/sector/VIX context conditioning** | Does conditioning the frozen baseline's entries on market/sector/VIX regime state improve it? | Same as baseline, extended to 10y for the final re-run | REJECTED — a real effect exists but reverses sign between 2016–2022 and 2022–2026 eras; neither of two pre-declared explanatory variables (realized volatility, India VIX) explains the reversal | `H_CONTEXT_*`, `H_TRANSMISSION_*` | CLOSED, standing-prohibited ("no third regime variable will be sought") |
| **Calendar / gap / breadth / sector rotation** | Do day-of-week effects, overnight gap-fade, market breadth, or sector-rotation ranking predict returns? | Same universes, 9–11 years | Real, replicated effects exist (Tuesday effect survives Bonferroni across 31/32 symbols) but are smaller than realistic transaction costs, lack an execution vehicle, or fail adversarial "try to kill it" validation (gap-fade) | `H_GAP_*`, `H_CALENDAR_*`, `H_BREADTH_001`, `H_SECTOR_ROTATION_001` | CLOSED |
| **Derivatives (futures basis/OI, options IV/skew)** | Do futures basis, OI change, or options IV level/skew add incremental predictive information beyond OHLCV? | Real Dhan futures/options data, verified back to 2015 | REJECTED — no meaningful incremental information at any of the 4 tested angles; a genuine Dhan API defect (current-expiry IV inaccessible) was found and disclosed along the way | `audit/derivatives_research/PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md` | CLOSED — terminal, next step must be a genuinely different information source |
| **ML (triple-barrier baseline)** | Does a supervised ML classifier (logistic regression, triple-barrier labeling) beat the deterministic baseline? | `data/ml_research/` feature/label store | REJECTED — "no evidence of economic edge" | [`PHASE_1_REPORT.md`](PHASE_1_REPORT.md) (see `docs/research/`) | CLOSED |
| **Corporate events (dividends)** | Does price exhibit tradable drift before or after a known ex-dividend date? | 1,149 real dividend events, 32-symbol NSE universe, 10y | REJECTED — statistically meaningless post-event; sign-unstable pre-event (two splits decisively negative, one positive) | `EDGE_DISCOVERY_FINAL_REPORT.md` §8–10, `H_EVENT_001`/`H_EVENT_002` | CLOSED |
| **Cross-sectional momentum, relative volume, relative volatility** | Do genuinely new cross-sectional mechanisms (momentum continuation, abnormal relative volume, abnormal relative volatility) — distinct from the closed laggard-reversal/regime-filter families — predict returns? | Same 32-symbol universe, 10y | REJECTED — momentum came back opposite-signed; relative volume/volatility both sign-unstable across splits | `EDGE_DISCOVERY_FINAL_REPORT.md` §8–10, `H_XMOM_001`/`H_XVOL_001`/`H_XVOLATILITY_001` | CLOSED |
| **Market microstructure** | Does observable order-flow/quote-imbalance information predict short-horizon returns after costs? | — | **Untestable** — no historical bid/ask or order-book data exists anywhere this project can access for free | `EDGE_DISCOVERY_FINAL_REPORT.md` §4 | CLOSED on data absence, never tested |

## The terminal conclusion

**NO DEMONSTRATED EDGE WITH CURRENT INFORMATION SET.** Real, statistically measurable
short-horizon price patterns were found more than once (cross-sectional laggard
reversal; point-in-time-corrected mean reversion; the Tuesday calendar effect; gap-fade)
— but every one of them died either at realistic transaction costs, at portfolio/
execution realism, at survivorship correction, or at adversarial "try to kill it"
validation. This is the central, repeated structural finding of the entire research
program: **measurement is not the same as a tradable edge**, and the gap between them
was where every promising-looking result actually failed. See
[`EDGE_DISCOVERY_FINAL_REPORT.md`](EDGE_DISCOVERY_FINAL_REPORT.md) for the full,
final, 18-section report and its exact recommendation on further spend.
