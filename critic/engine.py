"""The deterministic critic itself: `evaluate()` independently
re-examines an already-proposed BUY (a Decision + the Signal built from
it) against evidence decision_engine.rules.classify never looks at, and
against exposure/execution-safety state the caller has already gathered.

Pure function -- no I/O, no randomness, no LLM -- same posture as
decision_engine.rules.classify and risk.engine.RiskEngine.evaluate.
Every input the critic cannot itself observe (kill switch state,
existing orders/positions, a market regime report) is an explicit,
OPTIONAL parameter the caller supplies from whatever it already has on
hand; an omitted one makes the corresponding check `evaluated=False`,
never a silent pass.
"""

from datetime import datetime, timedelta, timezone

from critic.config import CriticConfig
from critic.models import CriticAssessment, CriticCheck, CriticCheckName, CriticCheckSeverity, CriticVerdict
from decision_engine.models import Decision, DecisionLabel
from market_intelligence.regime import BenchmarkContext
from paper.engine import _naive
from strategy.signal import Signal


class CriticUnavailableError(Exception):
    """Raised when evaluate() is called for a decision with no concrete
    trade to critique -- mirrors risk.sizing.SizingUnavailableError and
    predictions.tracker.PredictionUnavailableError's identical guard for
    the same underlying reason (only a BUY has price levels)."""


def evaluate(
    decision: Decision,
    signal: Signal,
    *,
    config: CriticConfig | None = None,
    now: datetime | None = None,
    kill_switch_active: bool | None = None,
    existing_pending_order: bool = False,
    existing_open_position: bool = False,
    benchmark_context: BenchmarkContext | None = None,
) -> CriticAssessment:
    if decision.label != DecisionLabel.BUY:
        raise CriticUnavailableError(
            f"Cannot critique a {decision.label.value} decision -- only BUY proposes a concrete trade to evaluate."
        )
    if decision.symbol != signal.symbol:
        raise CriticUnavailableError(f"Decision symbol {decision.symbol!r} does not match signal symbol {signal.symbol!r}.")

    config = config or CriticConfig()
    resolved_now = _naive(now or datetime.now(timezone.utc))

    checks: list[CriticCheck] = []

    # --- HARD checks ------------------------------------------------------

    kill_switch_evaluated = kill_switch_active is not None
    checks.append(CriticCheck(
        name=CriticCheckName.KILL_SWITCH, evaluated=kill_switch_evaluated,
        passed=(not kill_switch_active) if kill_switch_evaluated else True,
        severity=CriticCheckSeverity.HARD,
        detail=(
            "Kill switch is active -- execution safety blocks any new order." if kill_switch_evaluated and kill_switch_active
            else "Kill switch is not active." if kill_switch_evaluated
            else "Kill switch state not supplied -- not evaluated."
        ),
    ))

    market_context = decision.market_context
    context_evaluated = market_context is not None
    future_ts_passed = True
    if context_evaluated:
        future_ts_passed = _naive(market_context.as_of) <= resolved_now + timedelta(seconds=config.future_timestamp_tolerance_seconds)
    checks.append(CriticCheck(
        name=CriticCheckName.FUTURE_TIMESTAMP, evaluated=context_evaluated, passed=future_ts_passed,
        severity=CriticCheckSeverity.HARD,
        detail=(
            f"market_context.as_of ({market_context.as_of.isoformat()}) is ahead of now ({resolved_now.isoformat()}) beyond tolerance."
            if context_evaluated and not future_ts_passed
            else "market_context.as_of is not ahead of now." if context_evaluated
            else "No market_context supplied -- not evaluated."
        ),
    ))

    freshness_passed = True
    if context_evaluated:
        age_seconds = (resolved_now - _naive(market_context.as_of)).total_seconds()
        freshness_passed = age_seconds <= config.max_data_staleness_seconds
    checks.append(CriticCheck(
        name=CriticCheckName.DATA_FRESHNESS, evaluated=context_evaluated, passed=freshness_passed,
        severity=CriticCheckSeverity.HARD,
        detail=(
            f"market_context is {(resolved_now - _naive(market_context.as_of)).total_seconds():,.0f}s old, "
            f"exceeding the {config.max_data_staleness_seconds:,.0f}s limit." if context_evaluated and not freshness_passed
            else "market_context age is within the configured limit." if context_evaluated
            else "No market_context supplied -- not evaluated."
        ),
    ))

    structure_passed = signal.stop_price < signal.reference_price < signal.target_price
    structure_prefix = f"stop={signal.stop_price:.4f} entry={signal.reference_price:.4f} target={signal.target_price:.4f} -- "
    checks.append(CriticCheck(
        name=CriticCheckName.TRADE_STRUCTURE, evaluated=True, passed=structure_passed, severity=CriticCheckSeverity.HARD,
        detail=structure_prefix + ("sanely ordered." if structure_passed else "NOT sanely ordered; a long trade requires stop < entry < target."),
    ))

    duplicate_passed = not (existing_pending_order or existing_open_position)
    if duplicate_passed:
        duplicate_detail = f"{signal.symbol} has no pending order or open position."
    else:
        what = " and ".join(
            filter(None, ["a pending order" if existing_pending_order else "", "an open position" if existing_open_position else ""])
        )
        duplicate_detail = f"{signal.symbol} already has {what}."
    checks.append(CriticCheck(
        name=CriticCheckName.DUPLICATE_EXPOSURE, evaluated=True, passed=duplicate_passed, severity=CriticCheckSeverity.HARD,
        detail=duplicate_detail,
    ))

    scanner_evidence_passed = decision.scanner_evidence is not None
    checks.append(CriticCheck(
        name=CriticCheckName.EVIDENCE_COMPLETENESS_SCANNER, evaluated=True, passed=scanner_evidence_passed, severity=CriticCheckSeverity.HARD,
        detail="Scanner evidence is present." if scanner_evidence_passed else "No scanner evidence on this decision -- cannot justify a BUY.",
    ))

    # --- WARNING checks -----------------------------------------------------

    checks.append(CriticCheck(
        name=CriticCheckName.EVIDENCE_COMPLETENESS_MARKET_CONTEXT, evaluated=True, passed=context_evaluated, severity=CriticCheckSeverity.WARNING,
        detail="Market context is present." if context_evaluated else "No market context recorded on this decision.",
    ))

    research_evaluated = decision.research_evidence is not None
    checks.append(CriticCheck(
        name=CriticCheckName.EVIDENCE_COMPLETENESS_RESEARCH, evaluated=True, passed=research_evaluated, severity=CriticCheckSeverity.WARNING,
        detail="Research evidence is present." if research_evaluated else "No research evidence recorded on this decision.",
    ))

    volume_ratio = decision.scanner_evidence.volume_ratio if decision.scanner_evidence is not None else None
    volume_evaluated = config.min_volume_ratio is not None and volume_ratio is not None
    volume_passed = (volume_ratio >= config.min_volume_ratio) if volume_evaluated else True
    checks.append(CriticCheck(
        name=CriticCheckName.VOLUME_CONFIRMATION, evaluated=volume_evaluated, passed=volume_passed, severity=CriticCheckSeverity.WARNING,
        detail=(
            f"volume_ratio {volume_ratio:.2f} is below the {config.min_volume_ratio:.2f} minimum -- weak volume confirmation." if volume_evaluated and not volume_passed
            else f"volume_ratio {volume_ratio:.2f} meets the minimum." if volume_evaluated
            else "volume_ratio unavailable or check disabled -- not evaluated."
        ),
    ))

    macd_histogram = market_context.macd_histogram if context_evaluated else None
    momentum_score = decision.scanner_evidence.momentum_score if decision.scanner_evidence is not None else None
    indicator_evaluated = macd_histogram is not None and momentum_score is not None
    indicator_passed = True
    if indicator_evaluated:
        indicator_passed = macd_histogram == 0 or momentum_score == 0 or (macd_histogram > 0) == (momentum_score > 0)
    checks.append(CriticCheck(
        name=CriticCheckName.INDICATOR_CONTRADICTION, evaluated=indicator_evaluated, passed=indicator_passed, severity=CriticCheckSeverity.WARNING,
        detail=(
            f"MACD histogram ({macd_histogram:+.4f}) disagrees with the scanner's own momentum score ({momentum_score:+.2f})." if indicator_evaluated and not indicator_passed
            else "MACD histogram and scanner momentum agree (or are neutral)." if indicator_evaluated
            else "MACD histogram or scanner momentum score unavailable -- not evaluated."
        ),
    ))

    regime_evaluated = benchmark_context is not None and benchmark_context.trend_regime != "UNKNOWN"
    regime_passed = (benchmark_context.trend_regime != "DOWNTREND") if regime_evaluated else True
    checks.append(CriticCheck(
        name=CriticCheckName.REGIME_CONFLICT, evaluated=regime_evaluated, passed=regime_passed, severity=CriticCheckSeverity.WARNING,
        detail=(
            f"Benchmark {benchmark_context.symbol} is in a {benchmark_context.trend_regime} regime -- hostile for a fresh LONG." if regime_evaluated and not regime_passed
            else f"Benchmark regime ({benchmark_context.trend_regime}) is not hostile." if regime_evaluated
            else "No usable benchmark regime supplied -- not evaluated."
        ),
    ))

    rr_passed = signal.risk_reward >= config.min_risk_reward
    checks.append(CriticCheck(
        name=CriticCheckName.RISK_REWARD, evaluated=True, passed=rr_passed, severity=CriticCheckSeverity.WARNING,
        detail=(
            f"risk_reward {signal.risk_reward:.2f} is below the {config.min_risk_reward:.2f} advisory minimum."
            if not rr_passed else f"risk_reward {signal.risk_reward:.2f} meets the advisory minimum."
        ),
    ))

    confidence_passed = decision.confidence is not None
    checks.append(CriticCheck(
        name=CriticCheckName.CONFIDENCE_INTEGRITY, evaluated=True, passed=confidence_passed, severity=CriticCheckSeverity.WARNING,
        detail=(
            "Deterministic confidence score is present (decision_engine.confidence.compute_confidence)." if confidence_passed
            else "No deterministic confidence score is present on this decision."
        ),
    ))

    failed_hard = [c.name.value for c in checks if c.evaluated and not c.passed and c.severity == CriticCheckSeverity.HARD]
    failed_warning = [c.name.value for c in checks if c.evaluated and not c.passed and c.severity == CriticCheckSeverity.WARNING]

    # A clear, independently-verifiable HARD failure (kill switch active,
    # duplicate exposure, degenerate structure, ...) always takes priority
    # over INSUFFICIENT_EVIDENCE: "reject, and here is exactly why" is more
    # actionable than "can't tell" whenever both are true at once (e.g. the
    # kill switch is active AND market_context/research are also both
    # missing) -- found via self-review of the verdict-priority logic
    # before this was ever wired into a live path.
    insufficient_evidence = decision.market_context is None and decision.research_evidence is None

    if failed_hard:
        verdict = CriticVerdict.REJECT
        reasons = [next(c.detail for c in checks if c.name.value == name and c.evaluated and not c.passed) for name in failed_hard]
    elif insufficient_evidence:
        verdict = CriticVerdict.INSUFFICIENT_EVIDENCE
        reasons = ["Neither market context nor research evidence is available -- too little evidence to meaningfully critique this proposal."]
    elif len(failed_warning) >= config.downgrade_warning_threshold:
        verdict = CriticVerdict.DOWNGRADE
        reasons = [next(c.detail for c in checks if c.name.value == name and c.evaluated and not c.passed) for name in failed_warning]
    else:
        verdict = CriticVerdict.APPROVE
        reasons = ["All hard checks passed; warning checks stayed below the downgrade threshold."]

    return CriticAssessment(
        verdict=verdict, checks=tuple(checks), failed_checks=tuple(failed_hard), warnings=tuple(failed_warning),
        reasons=tuple(reasons), config_version=config.version_id(),
    )
