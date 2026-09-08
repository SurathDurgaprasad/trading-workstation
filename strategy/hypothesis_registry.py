"""Strategy science, Phase 4 (entry hypothesis research) -- a persistent,
structured record of every hypothesis considered about WHY
TrendMomentumBaseline shows no demonstrated edge, and what might (or,
based on evidence gathered so far, might not) change that. Mission's own
explicit instruction: "every strategy modification must be treated as an
experiment" and "do not implement all hypotheses at once."

BUILD THE REAL TRADING BRAIN mission: as of H_MEANREV_001, this registry
also covers hypotheses for genuinely INDEPENDENT strategy families
(mean reversion, breakout quality, cross-sectional relative strength --
the new mission's own Family B/C/D), not only modifications of
TrendMomentumBaseline -- the H_ENTRY_*/H_EXIT_* id prefixes stay scoped
to the baseline itself (Family A + its own exit-management variants);
a new family gets its own id prefix (e.g. H_MEANREV_*) so the id alone
signals which market mechanism is under test, never conflated with "one
more TrendMomentumBaseline tweak."

INDIAN TRADING DECISION BRAIN mission: H_CONTEXT_MARKET_*/H_CONTEXT_SECTOR_*/
H_CONTEXT_VIX_* test whether MARKET/SECTOR/VIX CONTEXT changes the
frozen baseline stock-level BUY condition's own forward returns -- a
different question from every prior family (which stock-level SIGNAL
works), asking instead whether CONTEXT can act as a genuine decision
filter on top of a signal already held fixed.

This is a plain, honest ledger, not a claim of completeness: most
entries are OPEN (not yet tested) by design -- populating a hypothesis
with a status of SUPPORTED/REJECTED/INCONCLUSIVE requires the
`evidence` field to cite something ACTUALLY measured this session
(a real backtest run, a real statistical test), never a plausible-
sounding guess. See each record's own `evidence` field for what was
(or was not) actually done.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class HypothesisStatus(str, Enum):
    OPEN = "OPEN"
    """Not yet tested -- no experiment has been run."""
    SUPPORTED = "SUPPORTED"
    """A real experiment was run and its result matches the hypothesis's
    own stated expected_effect."""
    REJECTED = "REJECTED"
    """A real experiment was run and its result contradicts the
    hypothesis."""
    INCONCLUSIVE = "INCONCLUSIVE"
    """Some real evidence exists, but it is insufficient (sample size,
    statistical power, or scope) to confidently support or reject."""


class HypothesisRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    description: str
    rationale: str
    expected_effect: str
    dataset_restrictions: str
    experiment_design: str
    success_criteria: str
    failure_criteria: str
    status: HypothesisStatus
    evidence: str
    """A summary of the ACTUAL evidence gathered this session, or an
    explicit "not yet tested" statement when status is OPEN -- the field
    that keeps this registry honest rather than aspirational."""


def build_hypothesis_registry() -> tuple[HypothesisRecord, ...]:
    """Returns a fresh tuple of every hypothesis considered so far.
    Deliberately a function, not a module-level constant, so the
    registry can later be extended to load from persisted storage
    (Phase 6's experiment registry) without changing this module's own
    public interface."""
    return (
        HypothesisRecord(
            hypothesis_id="H_ENTRY_001",
            description="Trend confirmation entry timing carries no meaningful directional edge, and may be worse than random.",
            rationale=(
                "TrendMomentumBaseline requires SMA20>SMA50 AND RSI14>50 AND MACD>signal AND rising volume "
                "simultaneously -- a 'confirmed trend' filter that, by construction, only fires AFTER a move has "
                "already happened, which can mean buying into short-term exhaustion rather than genuine continuation."
            ),
            expected_effect="If true, entry timing should perform no better than (or worse than) randomly-timed entries with identical stop/target/sizing/costs.",
            dataset_restrictions="41 real cached symbols (32 NSE, 9 US), 5 years daily bars, TrendMomentumBaseline's own real trade count per symbol.",
            experiment_design=(
                "300 Monte Carlo iterations of RandomEntryStrategy (backtesting/random_baseline.py), matched "
                "trade count per symbol, identical ATR-based stop/target/cost assumptions; compare the pooled mean "
                "return distribution against the real strategy's own pooled result."
            ),
            success_criteria="A low fraction of random iterations perform at least as well as the real strategy (entry timing carries real information).",
            failure_criteria="A high fraction of random iterations perform at least as well as the real strategy (entry timing carries no edge, or a negative one).",
            status=HypothesisStatus.SUPPORTED,
            evidence=(
                "96.0% of 300 random-entry Monte Carlo iterations performed at least as well as the real strategy "
                "(real strategy pooled mean return -0.64% vs random baseline's own average of -0.06%). Entry timing "
                "is not merely uninformative -- it measurably underperforms random chance."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_ENTRY_002",
            description="Volume confirmation improves continuation probability beyond trend+momentum alone.",
            rationale="Rising volume is commonly cited as confirming genuine participation behind a move rather than a low-conviction drift.",
            expected_effect="A strategy requiring trend+momentum+volume should outperform one requiring only trend+momentum.",
            dataset_restrictions=(
                "Same 41-symbol universe (32 NSE, 9 US), 5 years daily bars. Honest scope note: "
                "TrendMomentumBaseline already requires its own binary volume_trend==\"increasing\" condition -- "
                "this tests whether a STRICTER, continuous, development-period-quantile-based volume_ratio bar "
                "(quant_research/alpha_features.py's Phase 10 feature) adds further value beyond that existing "
                "loose gate, not \"volume vs. no volume at all\"."
            ),
            experiment_design=(
                "BUILD THE REAL TRADING BRAIN mission: quant_research/volume_signal.py's Phase 11 candidates "
                "(A_high_volume, B_low_volume, C_extreme_volume -- each a FilteredStrategy wrapping the frozen "
                "TrendMomentumBaseline with a volume_ratio quantile predicate, per-symbol thresholds frozen from "
                "that symbol's OWN development-period data only) had existed, unit-tested, since Phase 11 but "
                "were never run through the full universe dev/val/oos protocol. This mission added "
                "run_universe_volume_filter_experiment() to close that gap and ran it for real against the full "
                "41-symbol universe via backtesting.runner.run_full_backtest (unchanged -- no new engine code, "
                "this experiment touches no exit mechanics)."
            ),
            success_criteria="Adding the volume condition improves validation/out-of-sample expectancy without collapsing sample size below the statistical floor (30 trades).",
            failure_criteria="Adding volume either has no measurable effect or worsens expectancy.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe, all 41 backtested successfully (0 failed, 0 excluded "
                "for insufficient development-period volume_ratio data). "
                "A_high_volume (171/69/88 dev/val/oos trades): Development expectancy -0.72% "
                "(mean-return 95% CI [-1.34%, -0.10%], entirely negative) -> NEGATIVE_PERFORMANCE. Validation "
                "expectancy -0.70% -> STATISTICALLY_MEANINGLESS. Out-of-sample expectancy -0.32% -> "
                "STATISTICALLY_MEANINGLESS. PROMOTION VERDICT: REJECTED (development alone is decisive evidence "
                "against, per this project's own promotion rule -- any confidently NEGATIVE_PERFORMANCE split is "
                "disqualifying). "
                "C_extreme_volume (174/73/91 trades): Development expectancy -0.80% (CI [-1.42%, -0.19%]) -> "
                "NEGATIVE_PERFORMANCE. Validation -0.70% and out-of-sample -0.28%, both STATISTICALLY_MEANINGLESS. "
                "REJECTED for the same reason -- and its trade count (174 dev) is close to A_high_volume's own "
                "(171), confirming the 'extreme' candidate is dominated by its high-volume tail, not its low-volume one. "
                "B_low_volume (17/13/11 trades): every split below this project's own 30-trade minimum sample "
                "floor -- INSUFFICIENT_DATA, not evidence for or against; low-volume days are simply too rare "
                "under this filter to test with the available data. "
                "Bonferroni correction (family_size=3, applied to out-of-sample returns, corrected z=2.394): no "
                "candidate survives correction as positive -- unsurprising, since none was even directionally "
                "positive before correction. "
                "REJECTED overall: unlike H_EXIT_002's real directional improvement, none of these three volume-"
                "filter candidates shows any improvement over the frozen baseline's own already-negative "
                "performance (baseline development expectancy -0.78%, per H_EXIT_001's own evidence -- "
                "A_high_volume's -0.72% and C_extreme_volume's -0.80% are statistically indistinguishable from "
                "that, not better). A stricter, continuous volume bar on top of the baseline's existing binary "
                "volume gate does not improve continuation probability on this evidence."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_ENTRY_003",
            description="Pullback entries (buying a temporary dip within an established uptrend) outperform breakout-style confirmation entries.",
            rationale="A confirmation-style entry (as in H_ENTRY_001) may buy an already-extended price; a pullback entry waits for a retracement before committing.",
            expected_effect="A pullback-based entry rule should show a smaller mean adverse excursion (MAE) than the current strategy's own 3.30% figure.",
            dataset_restrictions="Same 41-symbol universe.",
            experiment_design="Not yet built.",
            success_criteria="Pullback variant beats TrendMomentumBaseline's pooled expectancy with sufficient sample size (>=30 trades).",
            failure_criteria="No improvement, or an improvement not statistically distinguishable from noise.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "STRATEGY EDGE DISCOVERY mission, Phase B (see docs/H_ENTRY_PULLBACK_EVALUATION.md for the full "
                "evidence): implemented as PullbackContinuationStrategy (strategy/pullback_continuation.py) -- "
                "uptrend + net-bullish momentum + RSI14 was >=55 two bars ago, has since cooled into [40,55], plus a "
                "same-day resumption close -- reusing TrendMomentumBaseline's own ATR-based stop/target verbatim. "
                "Run against the real 41-symbol universe, 5 years daily bars: only 14 development / 10 validation / "
                "5 out-of-sample trades (29 total, pooled) -- INSUFFICIENT_DATA, below the 30-trade floor even "
                "pooled across all three splits. The rule's five-way AND condition, with a specific 2-bar RSI-shape "
                "requirement, fires too rarely to be evaluated with confidence on the available data. Directionally "
                "favorable point estimates were observed (beats the frozen baseline's own per-trade mean, beats "
                "64% of random-baseline Monte Carlo iterations) but are not meaningful at this sample size. "
                "INCONCLUSIVE: not evidence against the underlying pullback idea, but evidence that this specific "
                "implementation cannot be tested as designed. Per the mission's own explicit instruction, the rule "
                "was NOT loosened and re-run to clear the sample floor -- that would be the prohibited "
                "'adjust until profitable' pattern. This result, combined with H_EXIT_002's own INCONCLUSIVE "
                "verdict, triggers the mission's stop condition; no further entry hypotheses were implemented."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_ENTRY_004",
            description="Momentum ACCELERATION (is momentum increasing, not merely positive) matters more than absolute momentum level.",
            rationale="RSI14>50 and MACD>signal are absolute-level conditions -- they do not distinguish momentum that is building from momentum that is already fading from a high level.",
            expected_effect="A strategy conditioning on momentum acceleration should show a higher win rate than one conditioning on momentum level alone.",
            dataset_restrictions="Same 41-symbol universe (32 NSE, 9 US), 5 years daily bars.",
            experiment_design=(
                "BUILD THE REAL TRADING BRAIN mission: strategy/momentum_acceleration.py -- three FilteredStrategy "
                "candidates wrapping the frozen TrendMomentumBaseline, gated on a signed 3-bar delta of an "
                "already-causal indicator (A: rsi_14.diff(3)>0, B: macd_histogram.diff(3)>0, C: both), the lookback "
                "chosen a priori and never tuned against any result. Run via "
                "run_universe_momentum_acceleration_experiment() -- a self-contained fetch/compute/split/run loop "
                "(mirroring backtesting.runner.run_full_backtest's own internal structure) rather than a direct "
                "call to that shared function, since it needed a column-injection step run_full_backtest exposes "
                "no hook for."
            ),
            success_criteria="Acceleration-based variant improves win rate/expectancy with sufficient sample size.",
            failure_criteria="No improvement.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe, all 41 backtested successfully (0 failed). "
                "A_rsi_accelerating (171/88/91 dev/val/oos trades): development expectancy -1.19% (mean-return "
                "95% CI [-1.76%, -0.62%], entirely negative) -> NEGATIVE_PERFORMANCE. Validation -0.69%, "
                "out-of-sample +0.02% (essentially flat), both STATISTICALLY_MEANINGLESS. "
                "B_macd_histogram_widening (146/75/85 trades): development expectancy -1.19% (CI [-1.82%, "
                "-0.56%]) -> NEGATIVE_PERFORMANCE. Validation -0.52%, out-of-sample -0.13%, STATISTICALLY_"
                "MEANINGLESS. "
                "C_both_accelerating (141/73/80 trades): development expectancy -1.09% (CI [-1.73%, -0.46%]) -> "
                "NEGATIVE_PERFORMANCE. Validation -0.53%, out-of-sample -0.19%, STATISTICALLY_MEANINGLESS. "
                "All three candidates: PROMOTION VERDICT REJECTED (a confidently NEGATIVE_PERFORMANCE development "
                "split is disqualifying per this project's own promotion rule, regardless of validation/OOS). "
                "Bonferroni correction (family_size=3, out-of-sample returns, corrected z=2.394): no candidate "
                "survives as positive. Unlike H_EXIT_002's real directional improvement, and unlike H_ENTRY_002's "
                "own OOS point estimates staying close to the baseline's, these three candidates' development "
                "expectancy (-1.09% to -1.19%) is MEANINGFULLY WORSE than the frozen baseline's own -0.78% "
                "(H_EXIT_001's evidence) -- gating on short-horizon momentum acceleration does not merely fail to "
                "help, it actively selects a worse subset of the baseline's own signals on this evidence."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_ENTRY_005",
            description="Regime filtering (only trading TrendMomentumBaseline's signals during a favorable market regime) improves expectancy.",
            rationale=(
                "Regime analysis (Phase 1, this session) found the dominant TRENDING_UP+NORMAL_VOLATILITY bucket "
                "(283 of 368 trades, Overall breakdown) is itself NEGATIVE_PERFORMANCE -- but every OTHER bucket "
                "had fewer than 30 trades, too few for a confident verdict either way."
            ),
            expected_effect="Restricting trading to a specific regime could change the pooled verdict, IF an untested smaller bucket genuinely differs -- but the ONE bucket with enough data to measure is also negative, so this is not promising on the evidence gathered so far.",
            dataset_restrictions="Same 41-symbol universe; every regime bucket other than TRENDING_UP+NORMAL_VOLATILITY has an insufficient sample size (<30 trades) in this dataset.",
            experiment_design=(
                "backtesting/regime.py's classify_trend_at/classify_volatility_at/group_trade_returns_by_regime "
                "already exist and were used for MEASUREMENT (Phase 1); no new strategy variant has been built that "
                "actually GATES entries by regime at signal-generation time."
            ),
            success_criteria="A regime-gated variant would need to show a credible POSITIVE_PERFORMANCE verdict in at least one regime bucket with >=30 trades.",
            failure_criteria="No regime bucket (in the current data) reaches a positive verdict with sufficient sample size.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "The ONLY regime bucket with sufficient sample size (TRENDING_UP+NORMAL_VOLATILITY, 283 trades) is "
                "itself NEGATIVE_PERFORMANCE, closely matching the overall pooled result. No evidence yet that ANY "
                "regime is favorable, but most regimes remain genuinely untested (too few trades), not proven "
                "negative. A regime-gated strategy variant has not been implemented or backtested."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_001",
            description="Moving the stop to breakeven once a position reaches +1R unrealized profit reduces the frequency of profitable trades reversing into losses.",
            rationale=(
                "Forensics (Phase 7C, weekend hardening cycle) found 44.4% of ALL losing trades had reached a "
                "favorable excursion of at least 50% of their own initial risk before ultimately reversing into the "
                "original, never-adjusted stop -- direct, structural evidence that some losers were, at one point, "
                "real winners."
            ),
            expected_effect="A meaningful fraction of trades currently classified as losers would instead close at breakeven (~0R) rather than -1R, improving pooled expectancy.",
            dataset_restrictions="Same 41-symbol universe; must preserve entry logic exactly (single-variable change) and validate on development/validation/out-of-sample splits separately, not the full pooled dataset alone.",
            experiment_design=(
                "Not yet implemented -- requires a new, clearly-labeled EXPERIMENTAL bar-processing variant that "
                "tracks each open position's own running favorable excursion and moves its stop to breakeven once "
                "it reaches +1R. Must NEVER modify backtesting/execution.py's shared, frozen check_exit() (which "
                "paper/engine.py's live trading path also depends on) -- the baseline's own historical results must "
                "never change silently."
            ),
            success_criteria="Development AND validation AND out-of-sample all show improved (or at least non-degraded) expectancy with sufficient sample size, and the effect is not explained by a handful of outlier trades.",
            failure_criteria="No improvement, improvement only in development (overfitting), or improvement driven by a small number of outliers.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Implemented in backtesting/exit_experiments.py (fully isolated from the frozen "
                "backtesting/execution.py path) and run against the real 41-symbol universe with the same "
                "development/validation/out-of-sample splits as the standard engine. Standard (unmodified) exit vs "
                "breakeven-at-+1R exit, same entry logic: "
                "Development 216->179 trades, win rate 30.56%->17.88%, expectancy -0.78%->-1.07%, profit factor "
                "0.666->0.445 (verdict stays NEGATIVE_PERFORMANCE, materially worse). "
                "Validation 108->114 trades, win rate 31.48%->27.19%, expectancy -0.70%->-0.56%, profit factor "
                "0.700->0.706 (verdict stays STATISTICALLY_MEANINGLESS; the only split with a marginal expectancy "
                "improvement, but win rate still drops). "
                "Out-of-sample 117->123 trades, win rate 38.46%->24.39%, expectancy -0.26%->-0.65%, profit factor "
                "0.873->0.640 (verdict WORSENS from STATISTICALLY_MEANINGLESS to NEGATIVE_PERFORMANCE). "
                "Two of three splits (development, out-of-sample) show clear degradation, not improvement -- moving "
                "the stop to breakeven at +1R cuts off trades that would have gone on to hit the 2:1 target, "
                "collapsing win rate far more than it rescues reversal-prone losers. REJECTED: fails the success "
                "criteria (all three splits must show non-degraded expectancy) and matches the stated failure "
                "criteria."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_002",
            description="Taking partial profit at +1R (closing part of the position) while letting the remainder run improves risk-adjusted expectancy.",
            rationale="Same forensics finding as H_EXIT_001 -- a partial exit locks in some gain from trades that later reverse, without fully capping upside on trades that continue favorably.",
            expected_effect="Reduced variance and improved expectancy relative to the current all-or-nothing stop/target structure.",
            dataset_restrictions="Same as H_EXIT_001.",
            experiment_design=(
                "Implemented in backtesting/exit_experiments.py (run_partial_profit_backtest / "
                "run_universe_partial_profit_experiment), same full-isolation posture as H_EXIT_001: closes floor(qty/2) "
                "of the original quantity at the +1R price level, remainder keeps the ORIGINAL, unmodified stop/target. "
                "Each split position produces two Trade records (a PARTIAL_TARGET leg and a final STOP/TARGET/"
                "END_OF_DATA leg); the single real entry fee is pro-rated across both legs rather than charged twice "
                "(dedicated test proves no double-counting)."
            ),
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "Run against the real 41-symbol universe with the same development/validation/out-of-sample splits as "
                "H_EXIT_001 and the standard engine. Standard (unmodified) exit vs partial-profit-at-+1R exit: "
                "Development 216->343 trade-records, expectancy -0.78%->+0.13% (mean CI [-0.27%,+0.52%]), profit "
                "factor 0.666->1.078 (verdict STATISTICALLY_MEANINGLESS). "
                "Validation 108->149 trade-records, expectancy -0.70%->+0.22% (mean CI [-0.41%,+0.85%]), profit "
                "factor 0.700->1.131 (STATISTICALLY_MEANINGLESS). "
                "Out-of-sample 117->160 trade-records, expectancy -0.26%->+0.49% (mean CI [-0.09%,+1.08%]), profit "
                "factor 0.873->1.330 (STATISTICALLY_MEANINGLESS). "
                "Every split flips from negative to positive point-estimate expectancy and profit factor climbs above "
                "1.0 in all three, with the effect size INCREASING out-of-sample rather than decaying -- the opposite "
                "of the textbook overfitting signature. However, every split's confidence interval still touches "
                "zero, so none reaches a POSITIVE_PERFORMANCE verdict -- this is a real, consistent, non-degraded "
                "directional improvement with adequate sample size, but not yet statistically decisive proof of an "
                "edge. Caveat: because a partial-take splits one logical position into two Trade records, the raw "
                "trade COUNT and any win-rate comparison are not directly apples-to-apples with the standard engine's "
                "one-record-per-position convention; profit factor and mean per-record return (dollar-weighted, not "
                "record-count-weighted) are the sound comparison points, and both improve consistently. INCONCLUSIVE: "
                "directionally supports the hypothesis, but the promotion bar (a confident positive verdict) has not "
                "been met -- must not be promoted on this evidence alone. "
                "STRATEGY EDGE DISCOVERY mission, Phase A -- full 12-step evaluation (see "
                "docs/H_EXIT_002_FULL_EVALUATION.md for the complete evidence): walk-forward across 6 real folds "
                "shows only 1 fold reaches POSITIVE_PERFORMANCE, the other 5 are STATISTICALLY_MEANINGLESS (2 with a "
                "slightly negative point estimate) -- the pooled dev/val/oos result is NOT stationarity-consistent. "
                "Regime analysis: the dominant TRENDING_UP+NORMAL_VOLATILITY bucket (385 trade-records) improves from "
                "the standard baseline's own NEGATIVE_PERFORMANCE to STATISTICALLY_MEANINGLESS -- a real, if modest, "
                "improvement in the strategy's own most common condition. Beats the random-entry baseline (16.0% of "
                "100 iterations matched or beat it) and beats the frozen baseline's own per-trade mean (+0.24% vs "
                "-0.62%). Survives realistic NSE cost/slippage sensitivity (edge shrinks roughly in half but stays "
                "positive in every split). Bonferroni correction (family_size=3, within-experiment) confirms no split "
                "reaches significance. UNITS-CORRECTED total-return comparison (the most important new finding): the "
                "candidate's own average TOTAL return per symbol over the full period is -0.81%, TRIVIALLY WORSE than "
                "the standard baseline's own -0.68%, and both lose decisively to buy-and-hold's +18.58% -- despite an "
                "improved per-trade-record expectancy, overall capital growth is not actually improved. Final "
                "verdict remains INCONCLUSIVE, not promoted; the exit-side research program (H_EXIT_001-004) is now "
                "exhausted -- no exit-logic variant tested demonstrates a real edge."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_003",
            description="An ATR-based trailing stop (the stop moves up as price advances, based on a multiple of ATR14) captures more of a favorable excursion than a static target.",
            rationale="Same forensics finding as H_EXIT_001/002 -- a trailing mechanism could realize more of the mean MFE (3.33%) than the current TARGET-or-STOP-only structure.",
            expected_effect="Improved expectancy, likely at the cost of a lower raw win rate (more trades trail out for a smaller gain than the current fixed 2:1 target would have captured).",
            dataset_restrictions="Same as H_EXIT_001.",
            experiment_design=(
                "Implemented in backtesting/exit_experiments.py (run_trailing_stop_backtest / "
                "run_universe_trailing_stop_experiment), same full-isolation posture as H_EXIT_001/002. Removes the "
                "fixed target entirely; the stop ratchets up using the SAME 1.5x-ATR14 multiplier strategy/"
                "baseline.py already uses for the original stop distance, recomputed from each bar's own current "
                "ATR. A bar's low is always checked against the level established by PRIOR bars, never a level "
                "just computed from that same bar's own high (see the module's own docstring for the ordering "
                "rationale)."
            ),
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe with the same development/validation/out-of-sample splits "
                "as H_EXIT_001/002. Standard (unmodified) exit vs ATR-trailing-stop exit: "
                "Development 216->221 trades, win rate 30.56%->30.77%, expectancy -0.78%->-0.48%, profit factor "
                "0.666->0.647 (stays NEGATIVE_PERFORMANCE; expectancy a bit less negative but profit factor still "
                "slipped). "
                "Validation 108->127 trades, win rate 31.48%->24.41%, expectancy -0.70%->-0.67%, profit factor "
                "0.700->0.530 (verdict WORSENS from STATISTICALLY_MEANINGLESS to NEGATIVE_PERFORMANCE -- a clear "
                "degradation, not an improvement). "
                "Out-of-sample 117->130 trades, win rate 38.46%->33.08%, expectancy -0.26%->-0.19%, profit factor "
                "0.873->0.850 (stays STATISTICALLY_MEANINGLESS; small expectancy gain, profit factor still slipped "
                "slightly). "
                "Results are mixed rather than consistently improved, and validation clearly degrades (both its "
                "verdict and its profit factor worsen materially) -- this fails the promotion rule's requirement "
                "that ALL three splits show non-degraded expectancy. REJECTED: unlike H_EXIT_002's consistent, "
                "growing improvement across all three splits, this trailing-stop variant does not reliably help and "
                "actively hurts the validation split."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_004",
            description="A time-based exit (force-close after N bars if neither stop nor target has been hit) improves expectancy by avoiding indefinite exposure to a stagnant thesis.",
            rationale="The current backtest strategy has NO time-based exit at all -- confirmed by reading backtesting/execution.py's check_exit(), which only ever returns STOP or TARGET.",
            expected_effect="Capping holding time could reduce exposure to slow-bleed trades and free capital for new signals sooner.",
            dataset_restrictions="Same as H_EXIT_001.",
            experiment_design=(
                "Implemented in backtesting/exit_experiments.py (run_time_based_exit_backtest / "
                "run_universe_time_based_exit_experiment) -- reuses backtesting.execution's own OpenPosition/"
                "check_exit/close_trade UNMODIFIED (this experiment does not touch the stop/target mechanic at "
                "all), adding only a bars-held counter that force-closes at ExitReason.EXPIRED (the same reason "
                "paper/engine.py's own live max_holding_bars mechanism uses) after DEFAULT_MAX_HOLDING_BARS=20 bars "
                "if neither stop nor target has been hit. The cap (20) was chosen from the real universe's own "
                "pooled holding-period distribution (median 7 / p75 19 / p90 29 calendar days across 441 standard-"
                "engine trades), not an arbitrary guess -- but that SAME analysis found winning trades hold LONGER "
                "than losing trades (winners' median 13 days vs losers' median 6 days), the opposite of the 'cut "
                "losers short' intuition the hypothesis assumes."
            ),
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe with the same development/validation/out-of-sample splits "
                "as H_EXIT_001/002/003. Standard (unmodified) exit vs 20-bar time-capped exit: "
                "Development 216->216 trades (identical count -- the cap almost never triggers here), win rate "
                "30.56%->31.02%, expectancy -0.78%->-0.75%, profit factor 0.666->0.657 (stays NEGATIVE_PERFORMANCE, "
                "no meaningful change). "
                "Validation 108->112 trades, win rate 31.48%->34.82%, expectancy -0.70%->-0.54%, profit factor "
                "0.700->0.734 (stays STATISTICALLY_MEANINGLESS; a small improvement, not decisive). "
                "Out-of-sample 117->118 trades, win rate 38.46%->38.14%, expectancy -0.26%->-0.36%, profit factor "
                "0.873->0.817 (stays STATISTICALLY_MEANINGLESS; a small DEGRADATION, not an improvement). "
                "Trade counts barely move in any split, confirming the cap rarely triggers at this threshold -- "
                "consistent with the a-priori concern that a cutoff near the overall p75 sits close to where "
                "genuine winners are still developing, offsetting whatever benefit it has against slow-bleeding "
                "losers. Net effect across all three splits is negligible-to-mixed, not a consistent improvement: "
                "REJECTED. Does not meet even H_EXIT_002's lower bar of a directionally consistent, growing signal."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_MEANREV_001",
            description=(
                "Short-term mean reversion: a symbol trading unusually far BELOW its own recent 20-day average "
                "(a large negative close z-score) tends to partially revert toward that average in the near term, "
                "independent of the symbol's longer-term trend direction."
            ),
            rationale=(
                "A genuinely INDEPENDENT market mechanism from Family A (trend continuation), which every "
                "H_ENTRY_*/H_EXIT_* hypothesis tested so far has been some variant of, all now resolved with zero "
                "promotions (see each record above). Overreaction correction, forced-seller exhaustion, and "
                "short-term liquidity-provider bargain-hunting are commonly cited economic reasons a sharp, "
                "short-term downside deviation partially reverts rather than persisting -- the opposite behavioral "
                "claim from momentum's own 'a move that has started tends to continue.'"
            ),
            expected_effect=(
                "A LONG-only strategy entering when zscore_close_20 is very negative should show a positive "
                "expectancy, distinct from (and not explained by) TrendMomentumBaseline's own trend-continuation logic."
            ),
            dataset_restrictions=(
                "Same 41-symbol universe (32 NSE, 9 US), 5 years daily bars. LONG-only, matching every other "
                "strategy in this project (no short-side mechanics exist or are introduced here)."
            ),
            experiment_design=(
                "Reuses quant_research/alpha_features.py's own zscore_close_20 (Phase 10, already causal, already "
                "unit-tested -- rolling 20-bar mean/std of close) rather than recomputing it. Three candidates, "
                "thresholds fixed a priori (not searched): A_oversold_2std (zscore_close_20 < -2.0, the standard "
                "textbook threshold), B_oversold_1_5std (< -1.5, a less extreme, more frequently-firing bar), "
                "C_oversold_within_uptrend (< -2.0 AND close > sma_200, reusing strategy/regime_filters.py's own "
                "broad-trend column -- 'buy a sharp dip, but only in a stock whose longer-term trend is still up', "
                "avoiding the 'catching a falling knife' failure mode a pure oversold-anywhere rule risks). Exit "
                "structure deliberately reuses TrendMomentumBaseline's own frozen stop/target constants (same "
                "isolation posture as quant_research/volume_signal.py's VolumeSignalStrategy) -- this experiment "
                "tests the ENTRY signal only, not a new exit design, which would confound two variables at once."
            ),
            success_criteria="Development AND validation AND out-of-sample all show a confident POSITIVE_PERFORMANCE verdict with sufficient sample size (>=30 trades pooled).",
            failure_criteria="Any split shows a confident NEGATIVE_PERFORMANCE verdict, or results are mixed/inconclusive across splits.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe, all 41 backtested successfully (0 failed). "
                "A_oversold_2std (288/94/96 dev/val/oos trades -- ample sample size in every split): development "
                "expectancy +0.09% and validation +0.13% (both STATISTICALLY_MEANINGLESS, point estimates barely "
                "positive), out-of-sample -0.26% (STATISTICALLY_MEANINGLESS, flips negative). PROMOTION VERDICT: "
                "REJECTED -- mixed, not consistently positive. "
                "B_oversold_1_5std (452/160/157 trades): development -0.16%, validation +0.22%, out-of-sample "
                "-0.10% -- also mixed. REJECTED. "
                "C_oversold_within_uptrend (54/23/29 trades): validation and out-of-sample both fall below the "
                "30-trade floor -- INSUFFICIENT_DATA. "
                "Bonferroni correction (family_size=3, out-of-sample returns, corrected z=2.394): no candidate "
                "survives as positive. "
                "Honest characterization, distinct from every other REJECTED verdict in this registry: A and B "
                "are NOT confidently negative like H_ENTRY_002/H_ENTRY_004/H_EXIT_001 were -- every point estimate "
                "sits close to zero with a wide confidence interval, and the specific pattern (positive in "
                "development/validation, negative out-of-sample) is the OPPOSITE of H_EXIT_002's own reassuring "
                "'effect growing out-of-sample' shape. This is far more consistent with pure sampling noise around "
                "a TRUE zero effect than with a real, suppressed signal -- REJECTED for being genuinely "
                "directionless, not for showing measurable harm. Family B (mean reversion) opens with a clean "
                "null result on this first, simplest operationalization of the mechanism; it does not by itself "
                "rule out every possible mean-reversion formulation (different lookback windows, different exit "
                "structure tied to reversion-to-mean rather than the baseline's fixed R:R, or a shorter holding "
                "horizon were not tested here and remain genuinely open questions, not evidence against)."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_RELSTRENGTH_001",
            description=(
                "A stock's own relative strength versus its market (trailing 20-bar return minus its benchmark "
                "index's own trailing 20-bar return) predicts forward continuation -- strong stocks keep "
                "outperforming weak ones."
            ),
            rationale=(
                "Family D (cross-sectional relative strength) per the BUILD THE REAL TRADING BRAIN mission's own "
                "explicit family list -- a genuinely independent mechanism from Family A (trend continuation, now "
                "fully exhausted, 9/9 hypotheses, zero promotions) and Family B (mean reversion, H_MEANREV_001, "
                "REJECTED). Relative-strength/cross-sectional-momentum effects are among the most widely "
                "replicated findings in the academic factor-investing literature."
            ),
            expected_effect=(
                "A LONG-only strategy entering when a symbol's relative_strength_20 is positive should show "
                "positive expectancy, and a STRONGER relative strength reading should show a stronger effect "
                "(monotonic dose-response across the three candidates)."
            ),
            dataset_restrictions=(
                "Same 41-symbol universe (32 NSE, 9 US), 5 years daily bars, plus each symbol's own benchmark "
                "index (^NSEI for .NS/.BO symbols, ^GSPC otherwise -- quant_research/alpha_features.py's own "
                "documented convention). LONG-only, matching every other strategy in this project. HONEST SCOPE "
                "NOTE: this tests SINGLE-SYMBOL relative strength as a standalone entry signal, NOT the mission's "
                "own 'Potential structure' for Family D (rank the whole universe, select the strongest "
                "percentile -- true cross-sectional selection). That needs a portfolio-level, shared-calendar "
                "backtesting engine this project's existing single-symbol backtesting/engine.py does not have; "
                "building one was judged out of proportion to test ONE hypothesis first ('do not add a giant "
                "feature blindly'). This narrower, still-independent question is tested first; the cross-sectional "
                "engine becomes a justified follow-up only if this shows real promise."
            ),
            experiment_design=(
                "quant_research/relative_strength_signal.py -- a STANDALONE Strategy (ignores SMA/RSI/MACD/volume "
                "entirely) reusing quant_research/alpha_features.py's own relative_strength_20 (Phase 10, already "
                "causal, already tested). Three candidates, thresholds fixed a priori as a monotonic dose-response "
                "ladder: A_any_outperformance (>0.0), B_meaningful_outperformance (>0.05), "
                "C_strong_outperformance (>0.10). Exit structure reuses TrendMomentumBaseline's own frozen "
                "stop/target, isolating the entry signal only. Run via "
                "run_universe_relative_strength_experiment() -- a self-contained fetch/compute/split/run loop "
                "(same reason as strategy/momentum_acceleration.py's and quant_research/mean_reversion_signal.py's "
                "own runners: needs a column-injection step run_full_backtest exposes no hook for -- here, also "
                "fetching a second series, the benchmark, which run_full_backtest has no concept of at all)."
            ),
            success_criteria="Development AND validation AND out-of-sample all show a confident POSITIVE_PERFORMANCE verdict with sufficient sample size (>=30 trades pooled), ideally with C > B > A (dose-response).",
            failure_criteria="Any split shows a confident NEGATIVE_PERFORMANCE verdict, or results are mixed/inconclusive across splits.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe plus each symbol's own benchmark (^NSEI/^GSPC), all 41 "
                "backtested successfully (0 failed). "
                "A_any_outperformance (395/165/266 dev/val/oos trades -- the LARGEST sample size of any hypothesis "
                "tested in this entire registry): development expectancy -0.67% (mean-return 95% CI [-1.12%, "
                "-0.23%], entirely negative) -> NEGATIVE_PERFORMANCE. Validation -0.43%, out-of-sample -0.36%, "
                "both STATISTICALLY_MEANINGLESS but both still negative point estimates. PROMOTION VERDICT: "
                "NEGATIVE. "
                "B_meaningful_outperformance (251/108/133 trades): all three splits STATISTICALLY_MEANINGLESS, "
                "point estimates -0.51%/-0.29%/-0.32% -- consistently negative but not confidently so. REJECTED "
                "(mixed, per the promotion rule -- no split confidently negative, but none positive either). "
                "C_strong_outperformance (99/35/49 trades): development expectancy -1.07% (CI [-2.02%, -0.12%]) "
                "-> NEGATIVE_PERFORMANCE, the MOST negative of the three candidates. PROMOTION VERDICT: NEGATIVE. "
                "Bonferroni correction (family_size=3, out-of-sample returns, corrected z=2.394): no candidate "
                "survives as positive -- unsurprising, none was directionally positive to begin with. "
                "NOTABLE FINDING, stated honestly rather than omitted: the hypothesis's own expected dose-response "
                "(C should show a STRONGER positive effect than A/B if the mechanism were real) is REVERSED in "
                "this data -- C's development expectancy (-1.07%) is roughly 60% worse than A's (-0.67%), meaning "
                "MORE extreme relative-strength readings correlate with WORSE forward performance, not better, on "
                "this evidence. This is consistent with buying already-extended relative strength being a form of "
                "buying exhaustion/overextension (echoing H_ENTRY_001's own finding that trend-confirmation entry "
                "timing underperforms random) rather than genuine continuation. REJECTED: on the single-symbol "
                "approximation tested here, relative strength shows no positive edge and the strongest readings "
                "are the worst performers, not the best -- the opposite of the hypothesis's own prediction. Does "
                "not test the mission's own true cross-sectional ranking/selection structure (see this record's "
                "own dataset_restrictions for why), which remains a genuinely open question."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_BREAKOUT_001",
            description=(
                "A Donchian-style breakout (close exceeds the prior 20-bar high) shows better forward continuation "
                "when accompanied by CONTEXT -- prior volatility contraction, or volume expansion on the breakout "
                "bar -- than a raw, unfiltered breakout."
            ),
            rationale=(
                "Family C (breakout quality) per the BUILD THE REAL TRADING BRAIN mission's own explicit family "
                "list: 'Test whether BREAKOUT + CONTEXT + LIQUIDITY + VOLATILITY produces better results than raw "
                "breakout.' A volatility squeeze preceding a breakout (the premise behind Bollinger/TTM squeeze "
                "indicators) and volume confirmation on the breakout bar itself are both commonly cited as "
                "distinguishing a genuine range expansion from a low-conviction false breakout."
            ),
            expected_effect=(
                "Candidates with CONTEXT (B: preceded by volatility contraction, C: accompanied by volume "
                "expansion) should show improved expectancy over the raw, unfiltered breakout (Candidate A)."
            ),
            dataset_restrictions="Same 41-symbol universe (32 NSE, 9 US), 5 years daily bars. LONG-only, matching every other strategy in this project.",
            experiment_design=(
                "quant_research/breakout_signal.py -- a STANDALONE Strategy (ignores SMA/RSI/MACD entirely) with "
                "a new, genuinely causal Donchian-high column (highest HIGH of the PRIOR 20 bars, shift(1) before "
                "rolling so today's own high never counts toward today's own ceiling) plus reuse of "
                "atr_pct_of_price (quant_research/alpha_features.py) and volume_ratio (already standard in "
                "market.indicators.compute_indicator_series's own output). Three a-priori candidates: "
                "A_raw_breakout (the baseline this hypothesis's own B/C are measured against -- no context "
                "filter), B_breakout_after_volatility_contraction (A AND atr_pct_of_price below its own trailing "
                "60-bar median), C_breakout_with_volume_expansion (A AND volume_ratio>1.5 on the breakout bar -- "
                "volume in a DIFFERENT role than H_ENTRY_002's own already-tested, already-REJECTED trend-"
                "continuation filter use). Exit structure reuses TrendMomentumBaseline's own frozen stop/target, "
                "isolating the entry signal only. Run via run_universe_breakout_experiment() -- a self-contained "
                "fetch/compute/split/run loop, same reason as every other new-family runner this session."
            ),
            success_criteria="B and/or C show a confident POSITIVE_PERFORMANCE verdict (all three splits) with sufficient sample size, and outperform A (the context genuinely adds value).",
            failure_criteria="Any candidate shows a confident NEGATIVE_PERFORMANCE verdict, or B/C show no improvement over A.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Run against the real 41-symbol universe, all 41 backtested successfully (0 failed). "
                "A_raw_breakout (313/111/123 dev/val/oos trades): development expectancy -0.49% (mean-return 95% "
                "CI [-0.95%, -0.02%], entirely negative) -> NEGATIVE_PERFORMANCE. Validation -0.38%, out-of-sample "
                "-0.56%, both STATISTICALLY_MEANINGLESS but still negative point estimates. PROMOTION VERDICT: "
                "NEGATIVE. "
                "B_breakout_after_volatility_contraction (139/76/79 trades): development -0.49%, validation "
                "-0.28%, out-of-sample -0.65% -- all three negative point estimates, none confidently so "
                "(STATISTICALLY_MEANINGLESS throughout). REJECTED (mixed) -- essentially IDENTICAL to A's own "
                "development expectancy, not an improvement. "
                "C_breakout_with_volume_expansion (136/44/57 trades): development expectancy -0.86% (CI [-1.54%, "
                "-0.17%]) -> NEGATIVE_PERFORMANCE, the WORST of the three candidates. PROMOTION VERDICT: NEGATIVE. "
                "Bonferroni correction (family_size=3, out-of-sample returns, corrected z=2.394): no candidate "
                "survives as positive. "
                "NOTABLE FINDING, stated honestly rather than omitted: the hypothesis's own expected effect (B/C "
                "context should IMPROVE on A's raw breakout) is REVERSED -- B is statistically indistinguishable "
                "from A, and C (volume-confirmed breakout) is measurably WORSE than A, not better. Neither "
                "'quiet before the breakout' nor 'real participation on the breakout bar' rescues the underlying "
                "signal; if anything the volume-confirmation filter selects a WORSE subset. REJECTED across all "
                "three candidates. "
                "CROSS-HYPOTHESIS PATTERN worth naming explicitly: this is the THIRD of this session's four new "
                "hypotheses (alongside H_ENTRY_002/004 and H_RELSTRENGTH_001) where 'buying into strength' -- by "
                "trend+volume confirmation, momentum acceleration, relative strength, or now breakout -- shows a "
                "confidently negative or reversed-from-expected result on this specific 41-symbol/5-year dataset, "
                "while H_MEANREV_001 (buying weakness) was merely directionless, not negative. Stated as an "
                "honest observation across this session's own evidence, not a new claim requiring its own "
                "dedicated statistical test."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_MEANREV_002",
            description=(
                "US-only extreme 5-day price weakness (trailing_return_5 below its own development-period 5th "
                "percentile) shows a real, forward-positive reversal at the 5-trading-day horizon specifically."
            ),
            rationale=(
                "TRADING BRAIN EXECUTION LOOP mission, Part D-G: a broad, 68-condition market-behavior sweep "
                "(quant_research/market_behavior.py) found this pattern; it then survived every adversarial check "
                "run against it (Part I): decisive positive mean forward return (CI excludes zero) at h=2,3,5,10 "
                "across development, validation, AND out-of-sample with a FROZEN (dev-fit-only) threshold; not "
                "concentrated in any single symbol (all 9 US symbols independently positive, range +1.0% to "
                "+3.7%); survives up to a 60bps round-trip cost assumption; and at h=5 specifically, remains "
                "decisive even under a conservative Bonferroni correction for the full 68-condition sweep this "
                "candidate was selected from (family_size=68, corrected z=3.376) in ALL THREE splits -- the only "
                "horizon that does. Distinct from H_MEANREV_001 (REJECTED): a different metric "
                "(trailing_return_5 percentile vs. zscore_close_20), market-SPECIFIC (US-only, not pooled with "
                "NSE) -- H_MEANREV_001's own pooled-market design may have diluted a real, US-specific effect "
                "into apparent noise, which this hypothesis exists to test directly as a real, tradeable "
                "strategy rather than a raw price-behavior observation alone."
            ),
            expected_effect=(
                "A LONG-only strategy entering on this frozen condition should show a confident "
                "POSITIVE_PERFORMANCE verdict (via this project's own promotion gate, applied to REAL simulated "
                "trades with the standard cost model and risk engine -- not the raw, cost-free price-return "
                "measurement the candidate was originally found with) in development, validation, AND "
                "out-of-sample."
            ),
            dataset_restrictions=(
                "US symbols only (AAPL, AMZN, GOOGL, JNJ, JPM, MSFT, NVDA, WMT, XOM) -- this hypothesis makes no "
                "claim about NSE. LONG-only, matching every other strategy in this project."
            ),
            experiment_design=(
                "quant_research/us_weakness_reversal_signal.py -- a STANDALONE Strategy computing "
                "trailing_return_5 INLINE from indicator_series['close'] (no precomputed column needed, so this "
                "reuses backtesting.runner.run_full_backtest and backtesting.exit_experiments."
                "run_universe_time_based_exit_experiment COMPLETELY UNCHANGED -- zero new runner code), gated on "
                "a hardcoded, documented, FROZEN threshold (-5.3477%, the exact 5th percentile of the real "
                "US-pooled development-period trailing_return_5 distribution, n=4928 -- computed once, never "
                "refit). Two candidates, testing whether the raw price-behavior edge survives becoming an "
                "actual, cost-aware, risk-sized strategy: A_atr_stop_target (the SAME frozen "
                "stop=1.5xATR/target=2:1 every other hypothesis in this project's history uses -- isolates "
                "whether the ENTRY signal alone works with a neutral, non-overfit exit) and "
                "B_five_bar_time_exit (force-close after exactly 5 bars if neither stop nor target hit -- "
                "directly informed by h=5 being the one horizon that survived Bonferroni correction in all "
                "three splits)."
            ),
            success_criteria="At least one candidate reaches a confident POSITIVE_PERFORMANCE verdict (development AND validation AND out-of-sample) via strategy.promotion_gate.evaluate_promotion, using REAL simulated trades (real costs, real risk sizing), not the raw price-behavior measurement alone.",
            failure_criteria="Neither candidate reaches PROMOTED -- i.e. the raw price-behavior edge does not survive becoming an actual, cost-aware, risk-sized trade.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "Run against the real 9-symbol US universe (all 9 backtested successfully, 0 failed) via "
                "backtesting.runner.run_full_backtest (Candidate A) and backtesting.exit_experiments."
                "run_universe_time_based_exit_experiment (Candidate B) -- both reused COMPLETELY UNCHANGED, no "
                "new runner code required. "
                "A_atr_stop_target (92/37/32 dev/val/oos trades): development expectancy +0.07% (win rate 37.0%, "
                "PF 1.02), validation +0.54% (win rate 37.8%, PF 1.21), out-of-sample +1.28% (win rate 50.0%, "
                "PF 1.59) -- every split POSITIVE and IMPROVING out-of-sample, but every mean-return 95% CI still "
                "straddles zero. PROMOTION VERDICT: INCONCLUSIVE. "
                "B_five_bar_time_exit (122/43/37 trades): development expectancy +0.41% (win rate 48.4%, "
                "PF 1.27), validation +0.82% (win rate 53.5%, PF 1.54), out-of-sample +0.86% (win rate 64.9%, "
                "PF 1.76) -- the SAME all-positive, improving-out-of-sample shape as Candidate A, consistently "
                "stronger on every metric in every split, but likewise no split reaches a decisive CI. PROMOTION "
                "VERDICT: INCONCLUSIVE. "
                "This is the SAME shape as H_EXIT_002's own INCONCLUSIVE result (real, consistent, non-degraded, "
                "OOS-growing directional signal -- the opposite of the textbook overfitting signature -- but not "
                "yet statistically decisive), and arguably the most rigorously pre-vetted candidate in this "
                "project's history before ever reaching a strategy backtest: the underlying raw price-behavior "
                "finding survived a 68-condition broad sweep, a frozen dev-fit threshold, per-symbol concentration "
                "checking (all 9 symbols independently positive), a 60bps cost-sensitivity check, AND a "
                "conservative Bonferroni correction for the full sweep -- and STILL, once turned into an actual "
                "risk-sized trade with a real stop, the promotion bar was not cleared. Honest interpretation: the "
                "raw market behavior (price tends to bounce after extreme 5-day weakness) is real and well-"
                "evidenced; whether it survives becoming a PROFITABLE TRADE depends heavily on execution "
                "mechanics -- Candidate B's own consistent edge over Candidate A across every metric suggests the "
                "ATR-based stop (designed for TrendMomentumBaseline's trend-following logic, reused here only for "
                "cross-hypothesis methodological consistency) may be actively hurting this specific, structurally "
                "different mean-reversion entry by exiting before the reversal completes -- a real, named lead for "
                "future exit research (Part K), not pursued further this session per this project's own "
                "'do not force trades, do not loosen anything to manufacture a promotion' discipline. Sample size "
                "(9 US symbols only) is also a genuine, named limitation: more trades would sharpen every "
                "confidence interval shown above one way or the other."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_TRANSMISSION_001",
            description=(
                "Nasdaq's prior-session return predicts NIFTY IT-sector stocks' own forward returns, with a "
                "genuine, correct overnight lag (US closes ~2:30am IST, well before NSE's own 9:15am IST open the "
                "SAME NSE trading day that session's information becomes available for)."
            ),
            rationale=(
                "INDIAN MARKET TRADING BRAIN mission, Family C (global -> India transmission) -- the mission's own "
                "explicitly named example. Indian IT services companies (TCS, Infosys, HCL Tech, Tech Mahindra, "
                "Wipro) derive substantial revenue from US clients; Nasdaq strength/weakness could plausibly "
                "transmit via shared investor sentiment and correlated fundamentals."
            ),
            expected_effect=(
                "A large negative Nasdaq prior-day return should predict negative forward returns for NIFTY "
                "IT-sector stocks; a large positive Nasdaq prior-day return should predict positive forward "
                "returns -- a symmetric transmission effect."
            ),
            dataset_restrictions=(
                "The 5 NSE IT-sector symbols in the existing 41-symbol universe (TCS.NS, INFY.NS, HCLTECH.NS, "
                "TECHM.NS, WIPRO.NS), 5 years daily bars, conditioned on ^IXIC (Nasdaq)."
            ),
            experiment_design=(
                "Reuses quant_research/market_behavior.py's build_universe_datasets/summarize_forward_returns "
                "unchanged. New alignment logic only: Nasdaq's own trailing 1-day return, forward-filled onto "
                "each IT stock's own NSE calendar -- the EXACT causal alignment pattern quant_research/"
                "alpha_features.py's own relative_strength_20 already uses. Threshold frozen from the "
                "development-period pooled distribution only (20th/80th percentile), applied unchanged to "
                "validation/out-of-sample. A real, serious data-integrity bug was found and fixed while running "
                "this exact study (see backtesting/cache.py's own commit history, 2026-09-08): 28 of 32 NSE "
                "research-universe symbols -- including 3 of these 5 IT stocks -- had silently degraded from "
                "5-year to 1-year cached depth; this hypothesis's own real evidence below is the CORRECTED, "
                "post-fix result, re-run after restoring genuine 5-year depth for all 5 IT symbols."
            ),
            success_criteria="Both directions (decline and advance) reach a confident, CI-excludes-zero mean forward return in development, validation, AND out-of-sample.",
            failure_criteria="Either direction fails to replicate decisively out-of-sample, or the two directions show inconsistent/asymmetric reliability.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "Run against the real, CORRECTED (post cache-depth-fix) 5-symbol NSE IT universe, frozen "
                "thresholds (development-period pooled, n=3680): p20=-1.10%, p80=+1.20%. "
                "NASDAQ_DECLINE (bottom 20% of Nasdaq's own prior-day return): development DECISIVE NEGATIVE at "
                "all 3 horizons tested (h=1/3/5, n=734, mean -0.61%/-0.68%/-0.79%). Validation DECISIVE NEGATIVE "
                "at all 3 horizons (n=172, mean -0.63%/-0.97%/-1.32%). Out-of-sample: DECISIVE NEGATIVE at h=1 "
                "only (n=179, mean -0.51%, CI [-0.80%,-0.21%]); h=3/h=5 still negative point estimates but CI "
                "touches zero. Every single period/horizon combination shows a NEGATIVE point estimate -- fully "
                "direction-consistent, degrading in significance (not reversing) out-of-sample. "
                "NASDAQ_ADVANCE (top 20%): development DECISIVE POSITIVE at all 3 horizons (n=735, mean "
                "+0.59%/+0.85%/+0.80%). Validation DECISIVE POSITIVE at all 3 horizons (n=210, mean "
                "+0.61%/+0.88%/+0.69%). Out-of-sample: NOT decisive at any horizon, AND the point estimates "
                "REVERSE sign (n=178-181, mean -0.11%/-0.05%/-0.56%) -- a genuine directional flip, not merely a "
                "loss of significance. "
                "Per-symbol concentration check (h=3, all periods pooled): well-balanced across all 5 IT stocks "
                "in both directions (decline: TCS -0.51%, INFY -0.68%, HCLTECH -0.41%, TECHM -0.84%, WIPRO "
                "-0.89%, n~217 each; advance: all 5 positive, n~225 each) -- not concentrated in any single "
                "symbol. INCONCLUSIVE overall, with a real, honest asymmetry: the DECLINE side is a real, "
                "consistent, still-directionally-intact signal that simply lost statistical power out-of-sample "
                "(smaller OOS sample, not a contradicting result); the ADVANCE side shows a materially weaker, "
                "genuinely reversing out-of-sample result and should be trusted less than the decline side. "
                "Not promoted (neither direction is decisive in all three splits); not rejected (the decline "
                "side's direction never flips, and both sides are strongly decisive in 2 of 3 splits with "
                "substantial, well-balanced sample sizes) -- a real, partial, asymmetric transmission signal, "
                "stronger for bad news than good news, consistent with well-documented 'bad news travels faster "
                "than good news' asymmetry in cross-market transmission generally (not verified against a "
                "specific academic source here, stated as a plausible economic prior only)."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_MARKET_001",
            description="The frozen baseline stock-level BUY condition (uptrend structure + bullish RSI momentum) performs better when the broader NIFTY 50 index is itself in an uptrend.",
            rationale=(
                "INDIAN TRADING DECISION BRAIN mission, Family A (market context conditioning), Phase 5. Naive "
                "prior: 'a rising tide lifts all boats' -- a stock signal should be more reliable when the whole "
                "market is supportive. The mission explicitly warns not to assume this and to let the data decide."
            ),
            expected_effect="Conditional forward returns for the baseline BUY condition should be higher, and/or its win rate higher, when market_trend_regime == TRENDING_UP versus unconditioned.",
            dataset_restrictions="Full 32-symbol NSE universe, 5 years daily, baseline BUY condition (see H_CONTEXT_MARKET_002 for its exact causal definition) conditioned on ^NSEI's own causal trend_regime (backtesting.regime.classify_trend_at applied to ^NSEI's own OHLCV).",
            experiment_design=(
                "Reuses quant_research/market_behavior.py's build_universe_datasets/measure_condition unchanged. "
                "New module quant_research/context_experiments.py adds only the missing piece: "
                "build_benchmark_regime_series() computes an EXTERNAL benchmark's own causal trend regime as a "
                "date-indexed series, and attach_external_regime() forward-fills it onto each stock's own "
                "SymbolDataset.frame -- the identical causal cross-market alignment pattern "
                "quant_research/alpha_features.py's relative_strength_20 already uses. Horizons 5/10 bars, "
                "development/validation/out-of-sample splits, NSE only."
            ),
            success_criteria="CI-excludes-zero positive mean forward return, higher than the unconditioned control, in development AND validation AND out-of-sample.",
            failure_criteria="No consistent improvement over the unconditioned control across splits, or a reversal/degradation versus control.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Control (unconditioned baseline BUY, NSE, full universe, h5/h10): development n=8517 "
                "+0.276%/+0.555% (both CI-decisive positive); validation n=2420 -0.218%/-0.311% (both CI-decisive "
                "NEGATIVE); out-of-sample n=2380/2345 -0.119%(CI touches zero)/-0.407%(CI-decisive negative). "
                "H_CONTEXT_MARKET_001 (BUY + NIFTY TRENDING_UP): development n=5554 +0.279%/+0.635% (similar to "
                "or slightly better than control); validation n=1358 -0.196%/-0.605% (still negative, h10 WORSE "
                "than control's -0.311%); out-of-sample n=859/852 -0.299%(worse than control)/+0.044%(CI includes "
                "zero, not decisive). No split shows a consistent, decisive improvement over the unconditioned "
                "control -- market-up conditioning does not help, and modestly hurts on some metrics (h10 "
                "validation). REJECTED: the naive 'rising tide lifts all boats' prior does not hold for this "
                "baseline signal."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_MARKET_002",
            description="The frozen baseline stock-level BUY condition performs better -- not worse -- when the broader NIFTY 50 index is in a DOWNTREND (the stock's own bullish structure diverges from, rather than confirms, the market).",
            rationale=(
                "INDIAN TRADING DECISION BRAIN mission, Family A, Phase 5, registered as the natural counterpart "
                "to H_CONTEXT_MARKET_001 -- explicitly testing the mission's own warning not to assume 'up market "
                "= better buys.' A stock showing genuine uptrend + bullish momentum WHILE the broader index falls "
                "is plausibly a more idiosyncratic, distinctive signal (real relative strength) than one that "
                "merely rides a market-wide rally, where many stocks trivially look bullish together."
            ),
            expected_effect="Conditional forward returns for the baseline BUY condition should be no worse than -- and plausibly better than -- the unconditioned control when market_trend_regime == TRENDING_DOWN.",
            dataset_restrictions="Same as H_CONTEXT_MARKET_001: full 32-symbol NSE universe, 5 years daily.",
            experiment_design="Identical machinery to H_CONTEXT_MARKET_001 (same regime series, same condition_fn structure with TRENDING_DOWN in place of TRENDING_UP).",
            success_criteria="CI-excludes-zero positive mean forward return, higher than the unconditioned control, in development AND validation AND out-of-sample.",
            failure_criteria="No improvement over control, or a reversal/degradation versus control in any split.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "H_CONTEXT_MARKET_002 (BUY + NIFTY TRENDING_DOWN), h5/h10: development n=963 +0.573%/+1.040% "
                "(both CI-decisive positive, both roughly DOUBLE the control's +0.276%/+0.555%); validation n=499 "
                "+0.760%/+1.536% (both CI-decisive POSITIVE, a striking reversal from the control's decisively "
                "NEGATIVE -0.218%/-0.311% in the same period); out-of-sample n=261 +0.094%(CI touches zero, not "
                "decisive, but POSITIVE point estimate vs. control's negative -0.119%)/-0.181%(CI includes zero, "
                "not decisive, but far less negative than control's decisively negative -0.407%). Direction is "
                "consistently positive-vs-control across all three splits; decisive in development and "
                "validation, not decisive (but never reversing to a clearly negative point estimate) "
                "out-of-sample -- the same 'real, consistent, OOS-power-loss-not-reversal' shape as this "
                "project's own H_MEANREV_002 and the decline side of H_TRANSMISSION_001. "
                "Per-symbol concentration check (h5, all periods pooled, n=1723 total): broad-based across the "
                "universe -- 24 of 31 symbols with a nonzero sample show a POSITIVE mean return (e.g. AXISBANK.NS "
                "n=46 +1.55%, EICHERMOT.NS n=107 +1.12%, NTPC.NS n=82 +1.19%, SBIN.NS n=48 +1.27%), only 7 "
                "negative and none with a large enough sample to be driving the pooled result alone (largest "
                "negative: HCLTECH.NS n=75 -0.55%). Not concentrated in a handful of names. "
                "Cost-sensitivity check: pooled h5/h10 mean (+0.555%/+0.999%) survives a conservative 20bps "
                "round-trip haircut comfortably (+0.355%/+0.799%). "
                "INCONCLUSIVE overall (out-of-sample does not reach a decisive CI), but a real, broad-based, "
                "economically coherent, cost-surviving finding -- not promoted only because out-of-sample power "
                "is limited (n=261, roughly a fifth of development's sample), not because the effect reverses. "
                "The same divergence pattern independently reappears at the sector level (see "
                "H_CONTEXT_SECTOR_002), which strengthens confidence this is a real, replicable market mechanism "
                "(idiosyncratic/counter-tape strength) rather than a single-family coincidence -- worth a "
                "dedicated, larger-sample re-test (a longer history, or a larger universe) before any "
                "strategy-level attempt, per this project's own 'prove the market behavior before building a "
                "strategy' discipline."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_MARKET_003",
            description="The frozen baseline stock-level BUY condition's forward returns vary meaningfully depending on NIFTY 50's own volatility regime (LOW/NORMAL/HIGH).",
            rationale="INDIAN TRADING DECISION BRAIN mission, Family A, Phase 5 -- mission's own explicit instruction not to assume high volatility is bad.",
            expected_effect="A consistent (same-direction, not necessarily positive) effect of NIFTY's own volatility regime on the baseline BUY condition's forward returns across development, validation, and out-of-sample.",
            dataset_restrictions="Same 32-symbol NSE universe; ^NSEI's own causal volatility_regime (backtesting.regime.classify_volatility_at, 60-bar lookback, same defaults as every other volatility classification in this project).",
            experiment_design="Same machinery as H_CONTEXT_MARKET_001/002, using quant_research/context_experiments.py's build_benchmark_volatility_series() in place of the trend variant.",
            success_criteria="A same-sign, non-reversing effect (versus the unconditioned control) across development, validation, and out-of-sample for at least one volatility bucket.",
            failure_criteria="The effect's sign reverses between splits (development vs. validation, or validation vs. out-of-sample), indicating noise rather than a stable regime effect.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "LOW_VOLATILITY, h5/h10: development n=368 +0.946%/+2.023% (both CI-decisive positive, looks "
                "very strong); validation n=201 -0.991%/-1.742% (both CI-decisive NEGATIVE -- a direct SIGN "
                "REVERSAL from development); out-of-sample n=67/56 -0.829%(CI touches zero)/-0.620%(CI includes "
                "zero), still negative point estimates. Development's apparently strong result does not survive "
                "even into validation, let alone out-of-sample -- the classic signature of fitting to a "
                "development-period idiosyncrasy, not a real regime effect. "
                "HIGH_VOLATILITY, h5/h10: development n=346 +1.236%/+2.234% (CI-decisive positive); validation "
                "n=0 (NIFTY recorded zero HIGH_VOLATILITY days under this condition in the validation window -- "
                "cannot be evaluated at all); out-of-sample n=115 +0.159%/-0.107% (both CI includes zero, not "
                "decisive). No usable validation evidence and an inconclusive out-of-sample result. "
                "NORMAL_VOLATILITY (the majority regime, ~91% of the sample) closely tracks the unconditioned "
                "control in every split, as expected. "
                "REJECTED for LOW_VOLATILITY specifically (clean sign reversal development->validation, the "
                "sharpest disqualifying pattern this project's own promotion-gate discipline looks for); "
                "HIGH_VOLATILITY is REJECTED for insufficient/non-decisive evidence rather than a reversal (no "
                "validation sample at all). Neither volatility bucket is a usable decision filter. Notably "
                "different in character from H_CONTEXT_MARKET_002's market-trend finding, which stayed "
                "directionally consistent (never reversed sign) across all three splits -- this contrast is "
                "itself useful evidence that the research methodology here correctly discriminates a real, "
                "stable pattern from an unstable/noisy one."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_SECTOR_001",
            description="The frozen baseline stock-level BUY condition performs better when the stock's own NIFTY sector index is itself in an uptrend (sector confirms the stock).",
            rationale="INDIAN TRADING DECISION BRAIN mission, Family B (sector context), Phase 6 -- explicitly marked HIGH PRIORITY in the mission. Natural sector-level counterpart to H_CONTEXT_MARKET_001.",
            expected_effect="Higher, CI-decisive-positive conditional forward returns versus the unconditioned control when the stock's own sector_trend_regime == TRENDING_UP.",
            dataset_restrictions=(
                "A 21-of-32-symbol sector-taggable subset of the NSE universe, mapped to 6 of the 9 "
                "market_intelligence.regime.NIFTY_SECTOR_INDICES via a conservative, high-confidence-only "
                "GICS-style mapping NOT sourced from an official NSE index constituent file (none integrated in "
                "this project): NIFTY_BANK (HDFCBANK/ICICIBANK/SBIN/KOTAKBANK/AXISBANK), NIFTY_IT "
                "(TCS/INFY/HCLTECH/TECHM/WIPRO), NIFTY_AUTO (MARUTI/EICHERMOT/HEROMOTOCO), NIFTY_PHARMA "
                "(SUNPHARMA/CIPLA/DIVISLAB/DRREDDY), NIFTY_FMCG (HINDUNILVR/ITC), NIFTY_FINANCIAL_SERVICES "
                "(BAJFINANCE/BAJAJFINSV). 11 symbols deliberately excluded rather than guessed: RELIANCE, LT, "
                "ASIANPAINT, BHARTIARTL, ADANIPORTS, GRASIM, ULTRACEMCO, TATASTEEL, COALINDIA, NTPC, POWERGRID."
            ),
            experiment_design="Same machinery as H_CONTEXT_MARKET_001, with each symbol's OWN sector index's causal trend regime attached (not the market-wide NIFTY 50) via a per-sector loop over quant_research/context_experiments.py's build_benchmark_regime_series/attach_external_regime.",
            success_criteria="CI-excludes-zero positive mean forward return, higher than the unconditioned (sector-taggable-subset) control, in development AND validation AND out-of-sample.",
            failure_criteria="No consistent improvement over control across splits.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Control (unconditioned baseline BUY, 21-symbol sector-taggable subset, h5/h10): development "
                "n=5154 +0.204%/+0.361%; validation n=1746 -0.201%/-0.214%; out-of-sample n=1451/1423 "
                "-0.115%/-0.413%. "
                "H_CONTEXT_SECTOR_001 (BUY + own sector TRENDING_UP): development n=3977 +0.274%/+0.473% "
                "(similar to control); validation n=1071 -0.432%/-0.529% (WORSE than control's -0.201%/-0.214%); "
                "out-of-sample n=986/968 -0.117%/-0.431% (essentially identical to control). Sector agreement "
                "does not improve on the unconditioned baseline in any split, and is measurably worse in "
                "validation. REJECTED: the naive 'sector confirms stock = better' prior does not hold, echoing "
                "H_CONTEXT_MARKET_001's identical finding at the market level."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_SECTOR_002",
            description="The frozen baseline stock-level BUY condition performs better -- not worse -- when the stock's own NIFTY sector index is in a DOWNTREND (the stock diverges from its own sector, echoing H_CONTEXT_MARKET_002's market-level divergence finding).",
            rationale="INDIAN TRADING DECISION BRAIN mission, Family B, Phase 6 -- registered specifically to test whether H_CONTEXT_MARKET_002's divergence effect replicates at the sector level, a genuinely independent context layer.",
            expected_effect="Conditional forward returns no worse than, and plausibly better than, the unconditioned control when sector_trend_regime == TRENDING_DOWN.",
            dataset_restrictions="Same 21-symbol sector-taggable subset as H_CONTEXT_SECTOR_001.",
            experiment_design="Identical machinery to H_CONTEXT_SECTOR_001, TRENDING_DOWN in place of TRENDING_UP.",
            success_criteria="CI-excludes-zero positive mean forward return, higher than the unconditioned control, in development AND validation AND out-of-sample.",
            failure_criteria="No improvement over control, or a reversal/degradation versus control in any split.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "H_CONTEXT_SECTOR_002 (BUY + own sector TRENDING_DOWN), h5/h10: development n=277 "
                "+0.327%/+0.655% (h10 CI-decisive positive, better than control's +0.204%/+0.361%); validation "
                "n=251 +0.556%/+0.895% (both CI-decisive POSITIVE, a reversal from control's decisively negative "
                "-0.201%/-0.214% -- the same shape as H_CONTEXT_MARKET_002's validation-split reversal); "
                "out-of-sample n=39 (small sample -- sector-disagreement while the stock is still technically "
                "bullish is a narrow condition) -0.072%/+0.732%, both CI includes zero, not decisive but not "
                "reversing to a clearly negative estimate either. Direction is consistently positive-vs-control "
                "in development and validation, echoing H_CONTEXT_MARKET_002 at an independent context layer; "
                "out-of-sample is underpowered (n=39) rather than contradicting. INCONCLUSIVE -- the smaller, "
                "narrower sector-taggable universe and the rarity of this specific condition (own sector down "
                "while the stock itself remains structurally bullish) limit out-of-sample confidence, but this "
                "is the SECOND independent context layer (after market-wide NIFTY) showing the same "
                "divergence-beats-confirmation shape, which is more valuable corroborating evidence than a "
                "second unrelated hypothesis would be. See H_CONTEXT_MARKET_002's evidence for the fuller, "
                "better-powered version of this same pattern and its concentration/cost checks."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_VIX_001",
            description="The frozen baseline stock-level BUY condition's forward returns are meaningfully different when India VIX is ELEVATED (level >= 1.3x its own 60-day trailing average) versus its DEPRESSED counterpart (<= 0.75x).",
            rationale="INDIAN TRADING DECISION BRAIN mission, Family C (India VIX / risk environment), Phase 7 -- mission's own explicit instruction not to assume high volatility is bad.",
            expected_effect="A consistent (same-direction, non-reversing) effect of India VIX regime on the baseline BUY condition's forward returns across development, validation, and out-of-sample.",
            dataset_restrictions="Full 32-symbol NSE universe; ^INDIAVIX's own causal regime via a new historical counterpart (quant_research/context_experiments.py's build_india_vix_regime_series) to market_intelligence.regime.compute_india_vix_context's existing latest-bar-only logic -- same thresholds (DEFAULT_VIX_LOOKBACK=60, ELEVATED>=1.3x, DEPRESSED<=0.75x trailing average), applied at every historical bar instead of only the most recent one.",
            experiment_design="Same machinery as H_CONTEXT_MARKET_001/002, VIX regime in place of NIFTY trend regime.",
            success_criteria="A same-sign, non-reversing effect across development, validation, and out-of-sample.",
            failure_criteria="The effect's sign reverses between any two splits.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "ELEVATED, h5/h10: development n=296 +0.434%(CI includes zero)/+1.404%(CI-decisive positive); "
                "validation n=54 +5.008%/+3.725% (both CI-decisive positive, an implausibly large effect for "
                "only 54 observations -- consistent with temporal clustering around one or two specific "
                "volatility-spike episodes rather than a broad, repeatable pattern); out-of-sample n=68 "
                "-1.124%/-2.468% (both CI-DECISIVE NEGATIVE -- a full sign reversal from validation). Development "
                "-> validation -> out-of-sample goes weak-positive -> extreme-positive -> decisive-negative: no "
                "usable, stable direction. REJECTED."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_VIX_002",
            description="Companion to H_CONTEXT_VIX_001: the DEPRESSED-VIX side of the same India VIX regime conditioning.",
            rationale="See H_CONTEXT_VIX_001.",
            expected_effect="A consistent (same-direction, non-reversing) effect across development, validation, and out-of-sample.",
            dataset_restrictions="Same as H_CONTEXT_VIX_001.",
            experiment_design="Same as H_CONTEXT_VIX_001, DEPRESSED in place of ELEVATED.",
            success_criteria="A same-sign, non-reversing effect across development, validation, and out-of-sample.",
            failure_criteria="The effect's sign reverses between any two splits.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "DEPRESSED, h5/h10: development n=81 +1.104%(CI-decisive positive)/-0.657%(CI includes zero); "
                "validation n=98 -1.594%/-2.480% (both CI-DECISIVE NEGATIVE -- reversal from development's h5 "
                "result); out-of-sample n=130 -1.012%/-1.144% (both CI-decisive negative, consistent with "
                "validation but not with development). No stable direction across splits. REJECTED. "
                "Combined with H_CONTEXT_VIX_001: neither VIX regime bucket survives dev->val->oos discipline, "
                "in clear contrast to H_CONTEXT_MARKET_002/H_CONTEXT_SECTOR_002's market/sector divergence "
                "finding, which stayed directionally consistent throughout -- India VIX regime, at least at "
                "these thresholds and this sample size, is not a usable decision filter for this baseline signal."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_ALIGN_001",
            description="Does the market-divergence effect (H_CONTEXT_MARKET_002) and the sector-divergence effect (H_CONTEXT_SECTOR_002) COMPOUND when both are true at once (stock bullish while BOTH its market and its own sector are falling), or does combining them just shrink the sample without adding signal?",
            rationale=(
                "INDIAN TRADING DECISION BRAIN mission, Family D (alignment/interaction), Phase 8 -- deliberately "
                "narrow and evidence-informed rather than a blind brute-force sweep of combinations, per the "
                "mission's own explicit warning against that. Only registered after Family A/B/C's own per-layer "
                "findings (context agreement never helps; context divergence helps at two independent layers) "
                "justified this specific question as the natural next one."
            ),
            expected_effect="If the two divergence effects are independent and additive, BOTH-diverge should show a stronger/more decisive effect than either single-layer divergence alone; if they are the same underlying effect measured twice, BOTH-diverge should look similar to either alone, just with a smaller sample.",
            dataset_restrictions="The same 21-symbol sector-taggable NSE subset as H_CONTEXT_SECTOR_001/002, both ^NSEI's own trend regime and each stock's own sector index trend regime attached simultaneously.",
            experiment_design=(
                "Same machinery as H_CONTEXT_MARKET_002/H_CONTEXT_SECTOR_002 (quant_research/context_experiments.py, "
                "unchanged), with BOTH market_trend_regime and sector_trend_regime attached to the same datasets and "
                "a compound condition_fn: baseline_buy_condition AND market_trend_regime == TRENDING_DOWN AND "
                "sector_trend_regime == TRENDING_DOWN. Compared against three counterparts: market-only-diverges "
                "(H_CONTEXT_ALIGN_002), sector-only-diverges (H_CONTEXT_ALIGN_003), and neither-diverges "
                "(H_CONTEXT_ALIGN_004, the natural control)."
            ),
            success_criteria="BOTH-diverge reaches a CI-decisive positive mean forward return, larger in magnitude than either single-layer divergence effect, in development AND validation AND out-of-sample.",
            failure_criteria="No improvement over the single-layer effects, or a reversal in any split with an adequate sample size.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "H_CONTEXT_ALIGN_001 (BOTH diverge), h5/h10: development n=159 +0.688%/+0.961% (both CI-decisive "
                "positive, larger than the neither-diverges control's +0.156%/+0.315%); validation n=226 "
                "+0.958%/+1.389% (both CI-decisive positive, and LARGER than either H_CONTEXT_MARKET_002's own "
                "validation result (+0.760%/+1.536%, comparable at h10, clearly larger at h5) or "
                "H_CONTEXT_SECTOR_002's (+0.556%/+0.895%) -- consistent with a genuine, real compounding effect "
                "rather than the same signal measured twice); out-of-sample n=10 (h5 -1.932%, h10 +0.472%, both "
                "CI wide and includes zero) -- the sample collapses to essentially unusable size once both "
                "conditions are required simultaneously on a 21-symbol universe. "
                "H_CONTEXT_ALIGN_002 (market diverges, sector does not), h5/h10: development n=451 "
                "+0.601%/+0.625% (both decisive positive); validation n=180 +0.279%(not decisive)/+1.963%(decisive "
                "positive); out-of-sample n=105 -0.424%(not decisive)/-1.728%(CI-decisive NEGATIVE) -- weaker and "
                "less consistent than the BOTH-diverge case, with a genuine h10 reversal out-of-sample. "
                "H_CONTEXT_ALIGN_003 (sector diverges, market does not), h5/h10: development not decisive "
                "(-0.159%/+0.243%, both CI includes zero); validation n=25 -3.076%/-3.575% (both CI-decisive "
                "NEGATIVE -- a sharp reversal, tiny sample); out-of-sample n=29 +0.569%/+0.821% (not decisive) -- "
                "no stable direction at all, smallest and noisiest of the four conditions. "
                "H_CONTEXT_ALIGN_004 (neither diverges, control): matches the general NSE baseline shape "
                "(development positive, validation/out-of-sample negative), as expected. "
                "INCONCLUSIVE, not REJECTED: the development+validation evidence for compounding is the single "
                "strongest, most decisive dev+val result in this whole research segment (stronger than either "
                "individual divergence layer), but out-of-sample statistical power (n=10) is far too small for "
                "any conclusion either way -- a genuine, honest data-limitation stop point for this specific "
                "narrow slice, not a contradicting result. Slicing this condition any further (e.g. by "
                "volatility bucket on top) would not be justified by the data available and was deliberately not "
                "attempted, per this project's own 'do not become speculative fishing' discipline."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_TRANSMISSION_002",
            description="USD/INR's prior-day return predicts NSE IT + Pharma exporter stocks' own forward returns.",
            rationale=(
                "NSE PREDICTION ENGINE mission, Family E (global -> India transmission), continuing "
                "H_TRANSMISSION_001's line of research with a second economically-motivated global signal. "
                "Indian IT and pharma companies derive substantial export revenue billed in USD; INR "
                "depreciation (USD/INR rising) should plausibly translate into HIGHER INR-denominated earnings "
                "for the same USD revenue, a real, named economic mechanism distinct from H_TRANSMISSION_001's "
                "sentiment-transmission story."
            ),
            expected_effect="USD/INR prior-day return in the top 20% (INR depreciating) should predict positive forward returns for NSE IT+Pharma exporters; bottom 20% (INR appreciating) should predict negative forward returns.",
            dataset_restrictions="9 NSE IT+Pharma symbols (TCS.NS, INFY.NS, HCLTECH.NS, TECHM.NS, WIPRO.NS, SUNPHARMA.NS, CIPLA.NS, DIVISLAB.NS, DRREDDY.NS), 5 years daily, conditioned on INR=X (USD/INR).",
            experiment_design=(
                "Reuses quant_research/market_behavior.py's build_universe_datasets/measure_condition unchanged. "
                "USD/INR's own prior-day return computed causally and forward-filled onto each stock's calendar -- "
                "the same alignment pattern as H_TRANSMISSION_001's Nasdaq alignment. Threshold frozen from the "
                "development-period pooled distribution only (20th/80th percentile), applied unchanged to "
                "validation/out-of-sample. Real infrastructure limitation found and worked around: "
                "backtesting.cache.CachedMarketDataProvider's own path-safety symbol validator rejects 'INR=X' "
                "(the standard Yahoo USD/INR ticker) because of its '=' character -- not a data problem, a "
                "filesystem-path-construction guard incidentally catching a legitimate forex ticker format. "
                "Worked around by fetching USD/INR uncached (a single fetch, acceptable cost) rather than "
                "loosening the path-safety validator for one symbol; the validator itself was correctly doing "
                "its job and was not modified."
            ),
            success_criteria="Both directions (INR depreciation and appreciation) reach a confident, CI-excludes-zero mean forward return in development, validation, AND out-of-sample, in the economically-predicted direction.",
            failure_criteria="Either direction fails to replicate decisively out-of-sample, reverses sign, or the pooled IT+Pharma result conceals sector-level disagreement.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "Frozen thresholds (development, n=6631, pooled across all 9 symbols): p20=-0.152%, p80=+0.172%. "
                "USDINR_RISING (INR depreciation), h1/h3/h5: development not decisive at any horizon (CI includes "
                "zero throughout); validation h1 not decisive, h3 -0.269%/h5 -0.382% (both CI-DECISIVE NEGATIVE -- "
                "the OPPOSITE sign of the economic prediction); out-of-sample not decisive at any horizon (point "
                "estimates near zero, mixed sign). USDINR_FALLING (INR appreciation), h1/h3/h5: development h3 "
                "+0.190% CI-decisive positive (matches the economic prediction's sign for THIS direction, "
                "inconsistently with the theory's own logic since a mirror-image effect would predict the "
                "opposite), h1/h5 not decisive; validation not decisive at any horizon; out-of-sample h3 -0.306% "
                "CI-decisive NEGATIVE -- a sign reversal from development. Neither direction shows a stable, "
                "theory-consistent, non-reversing effect across all three splits. "
                "CRITICAL SELF-CRITIQUE FINDING (per this project's own adversarial-review discipline -- 'could "
                "this be concentrated in one symbol/sector'): the per-symbol concentration check (h=3, "
                "USDINR_RISING, all periods pooled) reveals the pooled IT+Pharma universe was NOT a valid single "
                "group -- all 5 IT stocks show NEGATIVE mean returns (TCS -0.199%, INFY -0.262%, HCLTECH -0.180%, "
                "TECHM -0.043%, WIPRO -0.136%) while all 4 Pharma stocks show POSITIVE mean returns (SUNPHARMA "
                "+0.170%, CIPLA +0.154%, DIVISLAB +0.168%, DRREDDY +0.198%) under the IDENTICAL condition -- a "
                "real, clean, opposite-sign sector split that the pooled result completely conceals. REJECTED "
                "overall (no stable pooled effect survives dev/val/oos), with an explicit, honest design lesson: "
                "IT and Pharma should never have been pooled as a single 'exporter' bucket for this signal -- a "
                "genuine follow-up (not pursued this session) would test USD/INR -> IT and USD/INR -> Pharma as "
                "TWO SEPARATE hypotheses, since they may have genuinely different (or even opposite) real "
                "sensitivities this pooled test was structurally unable to detect."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_TRANSMISSION_003",
            description="USD/INR's prior-day return predicts NSE IT stocks' own forward returns, tested SEPARATELY from Pharma this time (see H_TRANSMISSION_002).",
            rationale=(
                "TRADING BRAIN mission, direct follow-up to H_TRANSMISSION_002's own finding that pooling IT and "
                "Pharma concealed opposite-signed behavior under the identical USD/INR condition. Re-run "
                "IT-only, same design."
            ),
            expected_effect="USD/INR rising (INR depreciation) predicts positive forward returns for NSE IT exporters; USD/INR falling predicts negative forward returns.",
            dataset_restrictions="5 NSE IT symbols (TCS.NS, INFY.NS, HCLTECH.NS, TECHM.NS, WIPRO.NS), 5 years daily, conditioned on INR=X.",
            experiment_design="Identical machinery and frozen-threshold discipline to H_TRANSMISSION_002, IT-only universe. Adversarial addition: the SAME 5 symbols' UNCONDITIONED (no USD/INR filter) forward returns were also measured across all three splits, to test whether any conditioned effect is genuinely incremental or just restates the sector's own baseline drift.",
            success_criteria="A conditioned effect that is decisive, theory-consistent, and MATERIALLY DIFFERENT from the unconditioned baseline across development, validation, AND out-of-sample.",
            failure_criteria="The conditioned result's shape (sign, magnitude) essentially matches the unconditioned baseline's own shape in the same splits -- meaning USD/INR carries no incremental information.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "USDINR_RISING, h1/h3/h5: development not decisive (-0.040%/-0.106%/-0.080%); validation h5 "
                "CI-decisive NEGATIVE (-0.558%) -- the OPPOSITE of the economic prediction; out-of-sample h1 "
                "CI-decisive negative (-0.213%). Point estimates negative at every horizon in every split "
                "(never flips sign), which looks superficially like a real, consistent effect. "
                "USDINR_FALLING: development not decisive but positive-leaning; validation mixed; out-of-sample "
                "h3/h5 CI-decisive NEGATIVE (-0.709%/-0.857%) -- a sign reversal from development, REJECTED on "
                "its own. "
                "DECISIVE ADVERSARIAL FINDING: IT's own UNCONDITIONED forward returns (no USD/INR filter at all) "
                "show the SAME shape as USDINR_RISING's conditioned result -- development roughly flat "
                "(+0.026%/+0.083%/+0.141%, mostly not decisive), validation CI-decisive NEGATIVE "
                "(-0.061%/-0.189%/-0.323%), out-of-sample CI-decisive NEGATIVE (-0.064%/-0.194%/-0.327%). IT "
                "stocks were simply in a negative-drift period during validation/out-of-sample REGARDLESS of "
                "USD/INR direction -- the conditioned result is substantially explained by this baseline drift, "
                "not a genuine incremental USD/INR transmission effect. REJECTED: USDINR_FALLING fails on its "
                "own sign-reversal; USDINR_RISING's apparent consistency does not survive the unconditioned-"
                "baseline comparison."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_TRANSMISSION_004",
            description="USD/INR's prior-day return predicts NSE Pharma stocks' own forward returns, tested SEPARATELY from IT (see H_TRANSMISSION_002).",
            rationale="Same as H_TRANSMISSION_003, Pharma-only.",
            expected_effect="USD/INR rising (INR depreciation) predicts positive forward returns for NSE Pharma exporters; USD/INR falling predicts negative forward returns.",
            dataset_restrictions="4 NSE Pharma symbols (SUNPHARMA.NS, CIPLA.NS, DIVISLAB.NS, DRREDDY.NS), 5 years daily, conditioned on INR=X.",
            experiment_design="Identical to H_TRANSMISSION_003, Pharma-only universe, same unconditioned-baseline adversarial comparison.",
            success_criteria="A conditioned effect decisive, theory-consistent, and materially different from the unconditioned baseline across all three splits.",
            failure_criteria="The conditioned result's shape matches the unconditioned baseline's own shape.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "USDINR_RISING, h1/h3/h5: development CI-DECISIVE POSITIVE at all 3 horizons (+0.129%/+0.284%/"
                "+0.320%) -- matches the economic prediction; validation NOT decisive and NEGATIVE-leaning "
                "(-0.067%/-0.232%/-0.165%, a real dip, not just noise); out-of-sample NOT decisive but "
                "positive-leaning again (+0.141%/+0.232%/+0.299%). "
                "USDINR_FALLING, h1/h3/h5: development not decisive, slightly positive; validation not decisive, "
                "positive; out-of-sample h5 CI-decisive POSITIVE (+0.373%) -- POSITIVE under BOTH USD/INR "
                "directions is the opposite of what a real bidirectional transmission effect should look like. "
                "DECISIVE ADVERSARIAL FINDING: Pharma's own UNCONDITIONED forward returns (no USD/INR filter) "
                "are ALSO decisively positive in development (+0.068%/+0.209%/+0.352%, all CI exclude zero) and "
                "directionally positive in out-of-sample (+0.054%/+0.147%/+0.243%, h5 CI-decisive) -- essentially "
                "the SAME shape as both conditioned directions. Pharma stocks simply drifted upward over this "
                "sample window regardless of USD/INR direction; USD/INR carries no incremental information over "
                "that baseline drift. REJECTED: the appearance of a theory-consistent effect on the RISING side "
                "is a restatement of Pharma's own unconditional drift, not a real transmission signal -- caught "
                "specifically by comparing against the unconditioned baseline, exactly the kind of adversarial "
                "check this project's own research discipline requires before trusting a promising-looking "
                "result."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_GAP_001",
            description="NSE stocks that open with a large overnight gap UP tend to give back part of that gap by the same day's close ('gap fade').",
            rationale=(
                "TRADING BRAIN mission, Family 1 (market structure) -- a classic, economically sensible "
                "microstructure hypothesis (overnight-gap overreaction, intraday mean reversion) not yet tested "
                "in this project's history. Genuinely new measurement dimension: every prior hypothesis measured "
                "N-BAR-AHEAD close-to-close forward returns; this measures the SAME bar's own open-to-close move, "
                "conditioned on how causally-known that bar's own open gapped from the PRIOR bar's close."
            ),
            expected_effect="Large gap-up opens (top decile of overnight gap %) show a negative same-day open-to-close return, more negative than the unconditioned baseline.",
            dataset_restrictions="Full 32-symbol NSE universe, 5 years daily, gap_pct = (open - prior_close) / prior_close computed causally per bar.",
            experiment_design=(
                "New standalone measurement (not quant_research/market_behavior.py's existing forward-return "
                "machinery, which cannot express a same-bar open-to-close outcome): gap_pct and intraday_return "
                "= (close - open) / open added directly to each build_universe_datasets() frame. Gap-size decile "
                "thresholds frozen from the development period only (pooled across all 32 symbols), applied "
                "unchanged to validation/out-of-sample. An UNCONDITIONED control (no gap filter) was measured "
                "in the same splits specifically to test whether any effect is incremental over the market's own "
                "typical same-day drift (the adversarial check H_TRANSMISSION_003/004 established the value of)."
            ),
            success_criteria="A CI-decisive negative same-day return, more negative than the unconditioned control, in development AND validation AND out-of-sample, that survives realistic NSE intraday round-trip costs (backtesting.costs.CostModel.india_nse_intraday_2026(), ~0.21% round trip).",
            failure_criteria="The effect reverses sign in any split, does not beat the unconditioned control, or does not survive realistic round-trip costs.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "Frozen thresholds (development, n=23645, pooled): p10=-0.629% (big gap down), p90=+0.839% "
                "(big gap up). "
                "GAP UP (top 10%): development n=2365 mean=-0.221% (CI-decisive negative, [-0.294%,-0.147%]); "
                "validation n=577 mean=-0.116% (CI [-0.253%,+0.021%], JUST touches zero, not quite decisive, "
                "same direction); out-of-sample n=687 mean=-0.133% (CI-decisive negative, [-0.258%,-0.007%]). "
                "Direction is negative in EVERY split, decisive in 2 of 3. "
                "UNCONDITIONED CONTROL (no gap filter): development -0.058%, validation -0.085%, "
                "out-of-sample -0.026% -- GAP UP's returns are MORE NEGATIVE than this control baseline in ALL "
                "THREE splits, meaning the effect is genuinely incremental, not a restatement of the market's "
                "own typical same-day drift (the exact confound that sank H_TRANSMISSION_003/004). "
                "Per-symbol concentration (full period pooled): broad-based -- 26 of 32 symbols show a negative "
                "mean return after a big gap up (e.g. MARUTI.NS -0.567%, NTPC.NS -0.477%, POWERGRID.NS -0.469%, "
                "BHARTIARTL.NS -0.522%, DRREDDY.NS -0.475%), only 6 mildly positive (largest: LT.NS +0.278%, "
                "n=101) -- not concentrated in a handful of names. "
                "COST REALITY CHECK (the decisive reason this is INCONCLUSIVE, not PROMOTED): "
                "backtesting.costs.CostModel.india_nse_intraday_2026() gives a realistic round-trip cost of "
                "~0.15% slippage (5bps entry + 10bps exit) + ~0.06% fees/taxes (2 fills) = ~0.21% round trip, "
                "before the flat Rs20-per-fill brokerage. A short-at-open/cover-at-close position capturing this "
                "effect would net: development +0.221%-0.21%=~+0.01% (barely positive, thin), validation "
                "+0.116%-0.21%=~-0.09% (NEGATIVE after costs), out-of-sample +0.133%-0.21%=~-0.08% (NEGATIVE "
                "after costs). The raw price behavior is real and broad-based; the effect size is comparable to "
                "or smaller than realistic transaction costs in 2 of 3 splits. "
                "ARCHITECTURAL REALITY CHECK: even setting costs aside, this project's execution/cost "
                "infrastructure (backtesting.costs.CostModel.slippage_adjusted_price, strategy/baseline.py) "
                "implements ONLY Side.LONG -- capturing the GAP UP side at all would require short-selling "
                "capability that does not exist anywhere in this codebase (by design; this project is "
                "structurally long-only) -- a real, structural, not-yet-addressed barrier to ever promoting "
                "this specific side, independent of the cost result above. "
                "INCONCLUSIVE: a real, broad-based, incremental (vs. baseline), non-reversing raw price effect -- "
                "but not shown to survive realistic costs in most splits, and not currently implementable as a "
                "strategy in this project's long-only architecture even if it did."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_GAP_002",
            description="NSE stocks that open with a large overnight gap DOWN tend to recover part of that gap by the same day's close.",
            rationale="Same as H_GAP_001, the symmetric gap-down side.",
            expected_effect="Large gap-down opens (bottom decile of overnight gap %) show a positive same-day open-to-close return, more positive than the unconditioned baseline.",
            dataset_restrictions="Same as H_GAP_001.",
            experiment_design="Same as H_GAP_001, gap-down (bottom decile) condition.",
            success_criteria="A CI-decisive positive same-day return, better than the unconditioned control, in development AND validation AND out-of-sample, surviving realistic round-trip costs.",
            failure_criteria="The effect reverses sign in any split, does not beat the unconditioned control, or does not survive realistic costs.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "GAP DOWN (bottom 10%): development n=2365 mean=+0.128% (CI-decisive positive, "
                "[+0.053%,+0.202%]); validation n=729 mean=+0.330% (CI-decisive positive, [+0.201%,+0.459%], "
                "the strongest single split of either gap direction); out-of-sample n=947 mean=+0.009% (CI "
                "[-0.102%,+0.119%], not decisive, essentially flat). Direction never reverses sign (positive "
                "or flat in every split), decisive in 2 of 3. "
                "Beats the unconditioned control (-0.058%/-0.085%/-0.026%, see H_GAP_001) in development and "
                "validation by a wide, decisive margin; out-of-sample is close to the control (+0.009% vs. "
                "-0.026%), a smaller but still favorable gap. "
                "COST REALITY CHECK: development +0.128%-0.21%=~-0.08% (NEGATIVE after ~0.21% realistic "
                "round-trip costs), validation +0.330%-0.21%=~+0.12% (the ONE split that survives), "
                "out-of-sample +0.009%-0.21%=~-0.20% (deeply negative after costs). Only 1 of 3 splits nets "
                "positive after realistic costs. "
                "ARCHITECTURAL NOTE: unlike H_GAP_001, this side (long at open, sell at close) is at least "
                "DIRECTIONALLY compatible with this project's long-only execution model -- but same-day, "
                "forced-exit-at-close intraday execution does not exist anywhere in backtesting/execution.py "
                "either (every existing strategy holds across multiple bars with a stop/target, never a forced "
                "same-bar exit), so this would still need genuinely new execution infrastructure to become a "
                "real strategy, not merely a sign-flip of an existing one. "
                "INCONCLUSIVE: real, non-reversing, broad raw price effect, stronger than H_GAP_001's on the "
                "development/validation splits, but out-of-sample weakens toward the control and does not "
                "clearly survive realistic costs in 2 of 3 splits -- not promoted, and would need new intraday "
                "execution infrastructure to ever be tested as a real strategy regardless."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_GAP_003",
            description=(
                "Deep validation of H_GAP_001/002 (overnight gap fade) -- a disciplined attempt to disprove the "
                "strongest raw finding in this project's history via cost sensitivity, pre-specified magnitude "
                "buckets, market-regime/VIX-regime/sector splits, a liquidity check, and year-concentration."
            ),
            rationale=(
                "EDGE VALIDATION mission, Phase 3's own explicit instruction: treat gap-fade as the "
                "highest-priority candidate and actively try to kill it before trusting it further. Every check "
                "below was chosen because it could disqualify the finding, not because it was expected to "
                "confirm it."
            ),
            expected_effect="The gap-fade effect should be broad-based, liquidity-independent, regime-stable, sector-diversified, and time-stable if it is a real, exploitable market mechanism rather than an artifact.",
            dataset_restrictions="Same full 32-symbol NSE universe as H_GAP_001/002, 5 years daily, plus NIFTY trend regime, India VIX regime, and market_intelligence.nse_sector_map sector tags attached per bar.",
            experiment_design=(
                "Six independent adversarial cuts, pre-specified before running (magnitude buckets: 0.5-1%, "
                "1-1.5%, 1.5-2%, 2-3%, 3%+, taken directly from this mission's own text, not fit to this data): "
                "(1) cost sensitivity across a 0.05%-0.30% grid on the full-period-pooled effect; (2) the "
                "magnitude buckets themselves; (3) NIFTY trend regime split; (4) India VIX regime split; (5) "
                "sector split via the existing NSE sector map; (6) liquidity split (above/below-median "
                "avg_daily_value); (7) year-by-year concentration, 2021-2026. A promising-looking extreme-tail "
                "sub-finding surfaced during (2) was explicitly flagged as EXPLORATORY (discovered by looking at "
                "results, not pre-registered) and re-tested with its own proper development/validation/"
                "out-of-sample split before being trusted at all, per this mission's own Phase 6 multiple-"
                "testing discipline."
            ),
            success_criteria="The effect survives realistic costs, is not concentrated in illiquid names or one sector, is stable across market/VIX regimes, and does not show a clear multi-year decay trend.",
            failure_criteria="Any of: fails to clear realistic round-trip costs; concentrates in below-median-liquidity names; concentrates in one sector; shows a clear decay trend across recent years; a sub-finding fails its own development-period check.",
            status=HypothesisStatus.REJECTED,
            evidence=(
                "COST SENSITIVITY (full-period pooled, n=3629 GAP UP / n=4041 GAP DOWN, short-the-gap-up / "
                "long-the-gap-down capture): raw GAP_UP capture +0.187% (CI-decisive), GAP_DOWN capture +0.136% "
                "(CI-decisive). Break-even: GAP_UP turns negative between 0.15% and 0.20% cost; GAP_DOWN turns "
                "negative between 0.10% and 0.15% cost. H_GAP_001's own registered realistic-cost estimate "
                "(~0.21% round trip, backtesting.costs.CostModel.india_nse_intraday_2026()) sits AT OR PAST both "
                "break-even points -- refines, does not reverse, the original INCONCLUSIVE-on-costs finding. "
                "MAGNITUDE BUCKETS (pre-specified): GAP UP fade is decisive-negative in the 0.5-1% (n=5956, "
                "-0.141%) and 1-1.5% (n=1485, -0.145%) buckets, NOT decisive in 1.5-2% (n=510, +0.046%, a "
                "non-monotonic dip -- CI includes zero, read as noise given the modest sample, not a real "
                "reversal), then decisive-negative again at 2-3% (n=315, -0.453%) and 3%+ (n=202, -0.581%). "
                "GAP DOWN recovery grows monotonically with magnitude and only the 0.5-1% bucket (n=3190, "
                "+0.086%) is individually decisive on its own; the apparently striking 3%+ bucket (n=203, "
                "+0.745%, would clear realistic costs by a wide margin) was investigated separately below. "
                "EXTREME-TAIL (3%+) GAP DOWN, PROPERLY RE-SPLIT: development n=97 mean=-0.205% (NOT decisive, "
                "and NEGATIVE -- the effect was not even present in the period it would need to be discovered "
                "in); validation n=45 mean=+1.998% (decisive positive); out-of-sample n=61 mean=+1.330% "
                "(decisive positive). Per-symbol counts in this bucket are tiny (many symbols n=1-6 over 5 "
                "years). REJECTED as its own claim: this is a textbook small-sample illusion that fails the "
                "most basic sequential validation logic (no real signal in development), not a genuine "
                "extreme-gap effect -- exactly the kind of exploratory, post-hoc-noticed result this project's "
                "own multiple-testing discipline exists to catch before it gets over-interpreted. "
                "MARKET REGIME SPLIT: GAP_UP fade is NOT decisive when NIFTY itself is TRENDING_UP (n=1196, "
                "-0.046%, CI includes zero) but IS decisive in TRENDING_DOWN (n=1396, -0.237%), SIDEWAYS "
                "(n=847, -0.279%), and UNKNOWN (n=188, -0.310%) -- a real, economically sensible regime "
                "dependence (a gap up against a falling/flat tape looks more like overreaction than one in a "
                "genuine uptrend), but it means the effect is NOT regime-stable, failing that specific success "
                "criterion. GAP_DOWN recovery is comparatively regime-stable (+0.182%/+0.127%/+0.096%/+0.121% "
                "across the four regimes, decisive in 3 of 4). "
                "VIX REGIME SPLIT: broadly consistent with the overall pattern in the NORMAL bucket (the large "
                "majority of the sample); ELEVATED and DEPRESSED buckets are too small (n=291/79 UP, n=567/43 "
                "DOWN) to add real information beyond the headline result. "
                "SECTOR SPLIT: GAP_UP fade is decisive only in NIFTY_PHARMA (n=306, -0.361%), NIFTY_AUTO "
                "(n=311, -0.261%), and NIFTY_FMCG (n=122, -0.314%); NOT decisive in NIFTY_BANK, NIFTY_IT, or "
                "NIFTY_FINANCIAL_SERVICES (all CI include zero, weaker point estimates around -0.10%). "
                "GAP_DOWN recovery is overwhelmingly concentrated in NIFTY_PHARMA alone (n=386, +0.518%, "
                "decisive and far larger than any other sector's point estimate, e.g. NIFTY_BANK's own barely-"
                "decisive +0.108%) -- a real, material sector concentration for the down side specifically, "
                "distinct from (and a sharper finding than) the whole-universe 27-of-32-symbols check H_GAP_001 "
                "already recorded. "
                "LIQUIDITY CHECK (the single most decisive disqualifying finding): GAP_UP fade is NOT decisive "
                "for ABOVE-median avg_daily_value stocks (n=2379, -0.066%, CI=[-0.145%,+0.012%]) but IS strongly "
                "decisive for BELOW-median-liquidity stocks (n=1250, -0.418%, CI=[-0.493%,-0.342%], nearly 6x "
                "the effect size and a much wider win-rate gap, 35.8% vs 47.1%) -- even within this large-cap-"
                "only universe, the effect is substantially a lower-liquidity phenomenon, exactly the kind of "
                "result this mission's own Phase 3 explicitly warns 'avoid strategies that depend on illiquid "
                "execution.' The realistic cost model used above almost certainly UNDERSTATES true slippage for "
                "the below-median-liquidity names actually driving the effect. "
                "YEAR CONCENTRATION: GAP_UP fade is decisive-negative in every year 2021-2024 but flattens to "
                "essentially zero in 2025 (n=508, +0.0004%, not decisive) and weakens (though still negative, "
                "not decisive) in 2026 (n=604, -0.130%) -- a real, honest recency-decay signal, consistent with "
                "either genuine regime change or the effect being arbitraged away, either of which argues "
                "against relying on the pooled 5-year average as a forward-looking estimate. "
                "FINAL VERDICT: REJECTED as a currently tradeable edge. The underlying raw phenomenon (moderate-"
                "size gap-fade, concentrated in less-liquid large caps) may still be real, but it fails multiple "
                "independent 'try to kill it' checks this mission specifically asked for: liquidity "
                "concentration, sector concentration (Pharma-driven on the down side), regime dependence "
                "(inert when NIFTY itself is rising), apparent recency decay, and a marginal-at-best cost "
                "margin. H_GAP_001/002's own original INCONCLUSIVE status is not overturned as a historical "
                "record of what was found and why it was promising at the time -- this entry is the deeper, "
                "harder look this mission demanded, and it does not survive."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_MARKET_004",
            description=(
                "Deep validation of the market/sector-divergence family (H_CONTEXT_MARKET_002/SECTOR_002/"
                "ALIGN_001) -- the SAME adversarial deep-validation treatment H_GAP_003 just applied to "
                "gap-fade, applied here to this project's other remaining INCONCLUSIVE candidate."
            ),
            rationale=(
                "EDGE VALIDATION mission, Phase 9's own priority rule (existing promising hypotheses come "
                "before new families). Gap-fade's deep validation (H_GAP_003) found real disqualifying issues "
                "when actually tried to be killed; this hypothesis had not yet received the same scrutiny and "
                "should not be trusted further without it, per H_GAP_003's own explicit warning."
            ),
            expected_effect="The market-divergence effect should survive realistic costs, not concentrate in illiquid names or one sector, and not show a clear multi-year decay trend, the same bar gap-fade failed.",
            dataset_restrictions="Same full 32-symbol NSE universe, 5 years daily, H_CONTEXT_MARKET_002's own condition (baseline BUY + NIFTY TRENDING_DOWN).",
            experiment_design=(
                "Four of H_GAP_003's five adversarial cuts, applied to the SAME condition_fn already registered "
                "under H_CONTEXT_MARKET_002: (1) cost sensitivity across a 0.05%-0.30% grid on the full-period-"
                "pooled h5/h10 mean forward return; (2) sector concentration via the existing NSE sector map; "
                "(3) liquidity split (above/below-median avg_daily_value); (4) year-by-year concentration, "
                "2021-2026. (Market/VIX-regime splits were not repeated -- this hypothesis IS itself a market-"
                "regime condition by construction, so slicing it by regime again would mostly just re-derive "
                "smaller versions of the same finding.) Structural note, unlike gap-fade: this hypothesis "
                "measures a multi-bar close-to-close forward return (quant_research/market_behavior.py's own "
                "fwd_return_h), directly implementable with this project's EXISTING long-only, multi-bar-hold "
                "backtesting engine -- no new same-day-exit or short-selling infrastructure would be needed to "
                "test this as a real strategy, unlike gap-fade."
            ),
            success_criteria="Survives realistic costs with margin, is decisive in BOTH liquidity halves (not just illiquid names), is not concentrated in one sector, and shows no clear decay trend.",
            failure_criteria="Fails to clear realistic costs, concentrates in illiquid names or one sector, or shows a clear decay trend -- the same bar gap-fade failed.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "COST SENSITIVITY (full-period pooled, n=1723): h5 mean=+0.555% (CI-decisive "
                "[+0.384%,+0.725%]), h10 mean=+0.999% (CI-decisive [+0.756%,+1.241%]). Remains POSITIVE at "
                "EVERY tested cost level up to 0.30% (h5 net=+0.255%, h10 net=+0.699% even at the highest cost "
                "tested) -- a materially wider cost margin than gap-fade's, which turned negative well before "
                "0.30%. Clears the realistic ~0.21% round-trip estimate comfortably in both horizons. "
                "SECTOR CONCENTRATION (h=5): NIFTY_BANK (n=220, +0.939%, CI-decisive) and NIFTY_AUTO (n=239, "
                "+1.064%, CI-decisive) are the strongest; NIFTY_IT (n=275, -0.176%, NOT decisive) is the ONLY "
                "sector with a negative point estimate -- a real, honest inconsistency, though NOT the kind of "
                "single-sector-dominates-everything pattern gap-fade's own recovery side showed (there, one "
                "sector explained nearly the entire pooled effect; here, two DIFFERENT sectors are each "
                "independently decisive and one is mildly negative, a materially healthier spread). "
                "NIFTY_PHARMA/FMCG/FINANCIAL_SERVICES are positive but not individually decisive (smaller "
                "samples, n=73-198). "
                "LIQUIDITY CHECK (h=5) -- the check that was MOST decisively disqualifying for gap-fade: "
                "ABOVE-median avg_daily_value stocks n=790, +0.344% (CI-decisive [+0.084%,+0.605%]); "
                "BELOW-median n=933, +0.732% (CI-decisive [+0.508%,+0.957%]). BOTH halves are independently "
                "CI-decisive -- roughly 2x stronger in the less-liquid half, but NOT inert in the more-liquid "
                "half the way gap-fade was. This is the clearest point of divergence from gap-fade's own "
                "liquidity result and the strongest piece of evidence this effect is not merely an illiquid-"
                "execution artifact. "
                "YEAR CONCENTRATION (h=5): 2021 +1.057% (decisive), 2022 +0.487% (decisive), 2023 +0.536% "
                "(decisive), 2024 +0.143% (not decisive, the weakest year), 2025 +1.020% (decisive, one of the "
                "strongest), 2026 (partial year) +0.094% (not decisive). No clean monotonic decay pattern like "
                "gap-fade's clean 2021-2024-strong-then-2025-2026-flat shape -- 2024 dips but 2025 recovers "
                "strongly, more consistent with normal year-to-year noise than a systematic fade. "
                "STILL INCONCLUSIVE, not upgraded: this deep-validation pass substantially STRENGTHENS "
                "confidence relative to gap-fade's own result on the same four checks (wider cost margin, both "
                "liquidity halves decisive, no clean decay pattern, less severe sector concentration) -- but it "
                "does not address the ORIGINAL, still-binding limitation already recorded under "
                "H_CONTEXT_MARKET_002/H_CONTEXT_ALIGN_001: thin out-of-sample statistical power (as low as n=10 "
                "for the compound market+sector-divergence condition). Robustness across cuts of the FULL-"
                "PERIOD sample is a different, necessary-but-not-sufficient claim from genuine out-of-sample "
                "decisiveness -- this entry answers 'is the effect an artifact of cost/liquidity/sector/time,' "
                "not 'does it hold on data the effect was never fit to.' The correct next step, if this line is "
                "pursued further, is growing the out-of-sample sample (a longer history and/or a larger, "
                "better-sourced sector map), not further robustness slicing of what's already available."
            ),
        ),
        HypothesisRecord(
            hypothesis_id="H_CONTEXT_MARKET_005",
            description=(
                "Re-run H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001 against genuine 10-year NSE history (up from "
                "5 years) -- H_CONTEXT_MARKET_004's own stated correct next step, growing out-of-sample "
                "statistical power rather than further robustness slicing."
            ),
            rationale=(
                "EDGE VALIDATION mission, Phase 9 priority rule. The 32-symbol universe (and the NIFTY/sector-"
                "index/India-VIX context tickers) were found to have genuine, clean 10-year Yahoo depth "
                "(verified via a real fetch before trusting it, per this project's own repeated cache-depth-"
                "incident lesson) -- refetched and cache-verified (main.py cache-status) before running any "
                "research against it."
            ),
            expected_effect="The market/sector-divergence effect should replicate with the same sign across a longer history, with a larger, more decisive out-of-sample sample.",
            dataset_restrictions="Same 32-symbol NSE universe (21 sector-taggable), now 10 years daily (2016-09-08 to 2026-09-08, ~2474 bars) instead of 5.",
            experiment_design=(
                "IMPORTANT METHODOLOGICAL CAVEAT, stated upfront: extending the period changes backtesting."
                "splits.split_periods' own 60/20/20 date boundaries -- this is NOT the original 5-year "
                "validation/out-of-sample data with more appended; it is an entirely new development "
                "(2016-2022) / validation (2022-2024) / out-of-sample (2024-2026) partition over a longer span. "
                "Treated honestly as an independent replication attempt over a different, larger sample, not as "
                "literally 'the same test with a bigger tail.' Same condition_fns as H_CONTEXT_MARKET_002/"
                "SECTOR_002/ALIGN_001, unchanged."
            ),
            success_criteria="The same sign and rough magnitude replicate across all three splits of the new, longer partition.",
            failure_criteria="The effect reverses sign between the new development period and the original finding, indicating the original result was specific to a sub-period rather than a stable mechanism.",
            status=HypothesisStatus.INCONCLUSIVE,
            evidence=(
                "UNCONDITIONED CONTROL, 10y, h5/h10: development (2016-2022) n=17375 +0.323%/+0.628% (CI-"
                "decisive positive); validation (2022-2024) n=6752 +0.328%/+0.723% (CI-decisive positive -- "
                "NOTE this reverses the original 5-year study's own validation sign, which was decisively "
                "NEGATIVE); out-of-sample (2024-2026) n=4785/4754 -0.173%/-0.361% (CI-decisive negative). The "
                "unconditioned baseline's own shape is now completely different once the window is extended -- "
                "a first sign that period selection materially changes this project's headline numbers. "
                "MARKET_DOWN (H_CONTEXT_MARKET_002's own condition), h5/h10: development n=1068 "
                "**-0.475%/-0.904% (CI-DECISIVE NEGATIVE)** -- the OPPOSITE SIGN of the original 5-year study's "
                "own development-period finding (+0.573%/+1.040%, decisively positive); validation n=537 "
                "+0.794%/+1.496% (CI-decisive positive); out-of-sample n=760 +0.531%/+0.946% (CI-decisive "
                "positive). The effect's sign is NOT stable across the full available history -- it is "
                "decisively NEGATIVE in 2016-2022 and decisively POSITIVE in 2022-2026, a genuine, previously-"
                "undetected time-instability the shorter 5-year window (which only ever covered the "
                "post-2021-positive era) could not have revealed, and which H_CONTEXT_MARKET_004's own year-by-"
                "year check (2021-2026 only) also could not have caught. "
                "SECTOR_DOWN, h5/h10: development n=702 -0.085%/-0.148% (NOT decisive, near flat -- less "
                "alarming than MARKET_DOWN's own reversal, but does not confirm the original positive finding "
                "either); validation n=168 +0.531%(not decisive)/+1.205%(CI-decisive positive); out-of-sample "
                "n=290 +0.472%/+0.873% (both CI-decisive positive). "
                "BOTH_DIVERGE (H_CONTEXT_ALIGN_001's own compound condition) -- THE ONE GENUINE IMPROVEMENT: "
                "development n=230 -0.104%/-0.324% (not decisive, mildly negative); validation n=81 "
                "+0.536%/+0.812% (not decisive, CI includes zero); **out-of-sample n=236 (up from the original "
                "study's own n=10) mean +0.836%/+1.350%, BOTH CI-DECISIVE POSITIVE** ([+0.378%,+1.294%] / "
                "[+0.742%,+1.959%]) -- genuinely solves the exact sample-size problem H_CONTEXT_MARKET_004 named "
                "as the binding constraint, for the first time giving this specific compound condition real "
                "out-of-sample statistical power. But development and validation do NOT confirm it under this "
                "particular partition, so it cannot be called decisive across all three splits. "
                "STILL INCONCLUSIVE, an honestly mixed result: this was NOT the clean confirmation hoped for. "
                "The market-level condition's sign instability across 2016-2022 vs. 2022-2026 is a real, "
                "material finding that argues AGAINST treating the original 5-year discovery as a stable, "
                "timeless mechanism -- it may instead be specific to the post-2021 market era this project's "
                "data happens to have been built around. The one genuine positive: the compound BOTH_DIVERGE "
                "condition's out-of-sample sample is now properly powered and decisive, which the original "
                "study's own n=10 could never have been. Do not promote on the strength of this entry alone -- "
                "the honest interpretation is that a longer history surfaced a real complication (period-"
                "dependence) at the same time it solved a real limitation (sample size), and both facts must be "
                "carried forward together, not selectively cited."
            ),
        ),
    )
