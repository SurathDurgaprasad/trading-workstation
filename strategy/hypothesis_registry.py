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
            experiment_design="Not yet implemented -- requires position-sizing-aware partial-exit logic, a larger change than H_EXIT_001's single-stop-adjustment.",
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.OPEN,
            evidence="Not yet implemented or tested this session.",
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_003",
            description="An ATR-based trailing stop (the stop moves up as price advances, based on a multiple of ATR14) captures more of a favorable excursion than a static target.",
            rationale="Same forensics finding as H_EXIT_001/002 -- a trailing mechanism could realize more of the mean MFE (3.33%) than the current TARGET-or-STOP-only structure.",
            expected_effect="Improved expectancy, likely at the cost of a lower raw win rate (more trades trail out for a smaller gain than the current fixed 2:1 target would have captured).",
            dataset_restrictions="Same as H_EXIT_001.",
            experiment_design="Not yet implemented.",
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.OPEN,
            evidence="Not yet implemented or tested this session.",
        ),
        HypothesisRecord(
            hypothesis_id="H_EXIT_004",
            description="A time-based exit (force-close after N bars if neither stop nor target has been hit) improves expectancy by avoiding indefinite exposure to a stagnant thesis.",
            rationale="The current backtest strategy has NO time-based exit at all -- confirmed by reading backtesting/execution.py's check_exit(), which only ever returns STOP or TARGET.",
            expected_effect="Capping holding time could reduce exposure to slow-bleed trades and free capital for new signals sooner.",
            dataset_restrictions="Same as H_EXIT_001.",
            experiment_design=(
                "Not yet implemented for the BACKTEST path -- paper/engine.py already has an unrelated "
                "max_holding_bars force-close mechanism for LIVE paper trading (built earlier this session), which "
                "could inform this experiment's design, but has not been ported or tested against historical data."
            ),
            success_criteria="Same as H_EXIT_001.",
            failure_criteria="Same as H_EXIT_001.",
            status=HypothesisStatus.OPEN,
            evidence="Not yet implemented or tested this session.",
        ),
    )
