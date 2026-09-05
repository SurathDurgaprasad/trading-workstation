"""Strategy science, Phase 4 (entry hypothesis research) -- a persistent,
structured record of every hypothesis considered about WHY
TrendMomentumBaseline shows no demonstrated edge, and what might (or,
based on evidence gathered so far, might not) change that. Mission's own
explicit instruction: "every strategy modification must be treated as an
experiment" and "do not implement all hypotheses at once."

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
            dataset_restrictions="Same 41-symbol universe.",
            experiment_design="Not yet built: would require an isolated 'trend+momentum, no volume filter' strategy variant, backtested and compared against TrendMomentumBaseline with dev/val/OOS splits.",
            success_criteria="Adding the volume condition improves validation/out-of-sample expectancy without collapsing sample size below the statistical floor (30 trades).",
            failure_criteria="Adding volume either has no measurable effect or worsens expectancy.",
            status=HypothesisStatus.OPEN,
            evidence="Not yet tested this session.",
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
            status=HypothesisStatus.OPEN,
            evidence="Not yet tested this session.",
        ),
        HypothesisRecord(
            hypothesis_id="H_ENTRY_004",
            description="Momentum ACCELERATION (is momentum increasing, not merely positive) matters more than absolute momentum level.",
            rationale="RSI14>50 and MACD>signal are absolute-level conditions -- they do not distinguish momentum that is building from momentum that is already fading from a high level.",
            expected_effect="A strategy conditioning on momentum acceleration should show a higher win rate than one conditioning on momentum level alone.",
            dataset_restrictions="Same 41-symbol universe.",
            experiment_design="Not yet built.",
            success_criteria="Acceleration-based variant improves win rate/expectancy with sufficient sample size.",
            failure_criteria="No improvement.",
            status=HypothesisStatus.OPEN,
            evidence="Not yet tested this session.",
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
                "been met -- must not be promoted on this evidence alone."
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
    )
