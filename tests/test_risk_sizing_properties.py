"""Autonomous hardening cycle 7 -- property-based tests for
risk/engine.py::RiskEngine.evaluate, the SOLE authority in this codebase
on "may this trade happen and how large" (see that module's own
docstring). Deliberately bounded and deterministic (max_examples capped,
derandomize=True) per this project's "no fake coverage / no meaningless
test explosion" discipline -- this is NOT fuzzing for its own sake, it
is a small number of targeted properties derived directly from
evaluate()'s own documented contract (fail-closed throughout; approve,
size, or reject; never fabricate a safe-looking decision from an unsafe
input).

Found a real, reproducible defect during the design of this suite (not
theoretical): a NaN target_price previously slipped past every existing
structural check and produced approved=True -- see
tests/test_risk_gates.py's "Non-finite values" section for the permanent
example-based regression, and risk/engine.py's evaluate() for the fix
(an explicit math.isfinite() guard). These property tests are the
generative complement to that fix: instead of re-asserting the one
input that happened to be found by hand, they sweep a bounded space of
adversarial combinations searching for any OTHER input that violates the
same "NaN/Inf never authorizes a trade" contract.
"""
import math
from datetime import datetime

from hypothesis import given, settings, strategies as st

from risk.account import Account, new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.veto import VetoReason
from strategy.signal import ReasonCode, Side, Signal

_PROPERTY_SETTINGS = settings(max_examples=150, derandomize=True)
"""derandomize=True: the exact same examples run every time, in every
environment -- a property test that only fails 1-in-N runs on a random
seed is worse than useless in CI (unreproducible red). max_examples=150:
enough to cover the adversarial strategies' interesting corners
(nan/inf/zero/negative are explicit members of every st.one_of below,
not left to chance discovery) without turning a full regression run
into a fuzzing marathon."""

_FINITE_POSITIVE_PRICE = st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False)
_ADVERSARIAL_PRICE = st.one_of(
    _FINITE_POSITIVE_PRICE,
    st.floats(min_value=-1e9, max_value=-0.01),
    st.just(0.0),
    st.just(float("nan")),
    st.just(float("inf")),
    st.just(float("-inf")),
)
_POSITIVE_RISK_REWARD = st.one_of(
    st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.just(float("inf")),
)
"""risk_reward's own Field(gt=0) already rejects NaN/-Inf/0/negative at
Signal construction time (nan > 0 and -inf > 0 are both False) -- this
strategy only ever generates values Pydantic will actually accept, so
Hypothesis spends its budget on values that reach RiskEngine.evaluate,
not on ValidationErrors that are Pydantic's own, already-tested
contract."""
_ADVERSARIAL_EQUITY = st.one_of(
    st.floats(min_value=1.0, max_value=1e12, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e9, max_value=-1.0),
    st.just(float("nan")),
    st.just(float("inf")),
    st.just(float("-inf")),
)


def _signal(*, reference_price: float, stop_price: float, target_price: float, risk_reward: float) -> Signal:
    return Signal(
        symbol="PROPTEST", generated_at=datetime(2024, 1, 1), side=Side.LONG,
        reference_price=reference_price, stop_price=stop_price, target_price=target_price,
        risk_reward=risk_reward, strategy_name="property-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )


def _account(*, cash: float) -> Account:
    # peak_equity/daily_start_equity deliberately fixed and decoupled from
    # `cash` -- isolates the property under test (does a non-finite/
    # adversarial EQUITY value ever authorize a trade) from the daily-
    # loss/drawdown circuit breakers, which are a separate, already-
    # covered concern (tests/test_risk_gates.py).
    return Account(initial_capital=100_000.0, cash=cash, peak_equity=100_000.0, daily_start_equity=100_000.0)


@_PROPERTY_SETTINGS
@given(
    reference_price=_ADVERSARIAL_PRICE, stop_price=_ADVERSARIAL_PRICE, target_price=_ADVERSARIAL_PRICE,
    risk_reward=_POSITIVE_RISK_REWARD, cash=_ADVERSARIAL_EQUITY,
)
def test_evaluate_never_raises_for_any_combination_of_adversarial_inputs(reference_price, stop_price, target_price, risk_reward, cash):
    """Robustness property: whatever combination of NaN/Inf/zero/negative/
    extreme values arrives, evaluate() must always return a RiskDecision
    -- never an unhandled exception. An uncaught crash deep in the risk
    engine is itself a failure-containment defect (it would take down
    whatever command called it, e.g. an entire scheduler tick) even when
    the crash happens to be "fail closed" in the narrow sense that no
    trade was placed."""
    engine = RiskEngine()
    signal = _signal(reference_price=reference_price, stop_price=stop_price, target_price=target_price, risk_reward=risk_reward)
    account = _account(cash=cash)
    engine.evaluate(signal, account)  # must not raise


@_PROPERTY_SETTINGS
@given(
    reference_price=_ADVERSARIAL_PRICE, stop_price=_ADVERSARIAL_PRICE, target_price=_ADVERSARIAL_PRICE,
    risk_reward=_POSITIVE_RISK_REWARD, cash=_ADVERSARIAL_EQUITY,
)
def test_non_finite_input_never_authorizes_a_trade(reference_price, stop_price, target_price, risk_reward, cash):
    """The core property this cycle's real defect violated: if ANY of
    the safety-relevant numeric inputs is NaN or +/-Inf, the resulting
    decision must never be approved, and the specific NON_FINITE_VALUE
    veto reason must be present so the rejection is diagnosable, not a
    decision that merely happens to fail some unrelated check."""
    engine = RiskEngine()
    signal = _signal(reference_price=reference_price, stop_price=stop_price, target_price=target_price, risk_reward=risk_reward)
    account = _account(cash=cash)
    values = (reference_price, stop_price, target_price, risk_reward, account.equity)
    any_non_finite = not all(math.isfinite(v) for v in values)

    decision = engine.evaluate(signal, account)

    if any_non_finite:
        assert not decision.approved
        assert VetoReason.NON_FINITE_VALUE in decision.veto_reasons


@_PROPERTY_SETTINGS
@given(
    reference_price=_ADVERSARIAL_PRICE, stop_price=_ADVERSARIAL_PRICE, target_price=_ADVERSARIAL_PRICE,
    risk_reward=_POSITIVE_RISK_REWARD, cash=_ADVERSARIAL_EQUITY,
)
def test_quantities_are_never_negative(reference_price, stop_price, target_price, risk_reward, cash):
    """requested_quantity/approved_quantity are share counts -- a
    negative quantity is meaningless and would be a silent numeric-sign
    defect if it ever occurred (e.g. from an unguarded floor-division by
    a negative risk_per_unit)."""
    engine = RiskEngine()
    signal = _signal(reference_price=reference_price, stop_price=stop_price, target_price=target_price, risk_reward=risk_reward)
    account = _account(cash=cash)

    decision = engine.evaluate(signal, account)

    assert decision.requested_quantity >= 0
    assert decision.approved_quantity >= 0


@_PROPERTY_SETTINGS
@given(
    reference_price=_ADVERSARIAL_PRICE, stop_price=_ADVERSARIAL_PRICE, target_price=_ADVERSARIAL_PRICE,
    risk_reward=_POSITIVE_RISK_REWARD, cash=_ADVERSARIAL_EQUITY,
)
def test_non_positive_stop_distance_never_produces_an_approved_trade(reference_price, stop_price, target_price, risk_reward, cash):
    """If reference_price <= stop_price (a zero or inverted/negative
    stop distance -- the stop is not actually below entry for a LONG),
    the trade must never be approved, regardless of any other field.
    Restricted to the finite-comparable case (NaN/Inf combinations are
    already covered, and asserted more strongly, by the two properties
    above)."""
    if not (math.isfinite(reference_price) and math.isfinite(stop_price)):
        return
    if reference_price > stop_price:
        return  # a genuinely valid stop distance -- not the case under test

    engine = RiskEngine()
    signal = _signal(reference_price=reference_price, stop_price=stop_price, target_price=target_price, risk_reward=risk_reward)
    account = _account(cash=cash)

    decision = engine.evaluate(signal, account)

    assert not decision.approved


@_PROPERTY_SETTINGS
@given(cash=st.floats(min_value=1_000.0, max_value=1e9, allow_nan=False, allow_infinity=False), risk_per_trade_pct=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False))
def test_approved_risk_never_exceeds_the_configured_budget(cash, risk_per_trade_pct):
    """When a trade IS approved, its total_risk must never exceed the
    equity-proportional budget the config authorizes -- quantity is
    floor-rounded specifically so this holds (never rounds up into an
    over-budget position)."""
    config = RiskConfig(risk_per_trade_pct=risk_per_trade_pct, max_exposure_pct=100.0)
    engine = RiskEngine(config)
    account = new_account(cash)
    signal = _signal(reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0)

    decision = engine.evaluate(signal, account)

    if decision.approved:
        risk_budget = account.equity * risk_per_trade_pct / 100
        assert decision.risk_amount <= risk_budget + 1e-9  # floating-point slack only
