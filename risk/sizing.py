"""Phase 22 -- bridges decision_engine's BUY/WATCH/AVOID/EXIT/NO_ACTION
labels to the EXISTING, UNCHANGED RiskEngine/Account/RiskConfig dynamic
position-sizing math (Phase 3/4 -- still the sole authority on "may this
trade happen and how large"). Adds nothing new to risk sizing itself:
risk/engine.py, risk/config.py, and risk/account.py are not modified,
because they already implement exactly what the roadmap's Phase 22
feature list asks for -- dynamic (never-hardcoded) capital via
Account.equity/initial_capital, risk-per-trade via RiskConfig.
risk_per_trade_pct, a daily-loss limit, position size computed fresh
from CURRENT equity every call, and a max-exposure limit.

The genuine gap: RiskEngine.evaluate(signal, account) requires a
fully-formed strategy.signal.Signal with concrete stop_price/
target_price -- decision_engine.models.Decision (Phase 21) deliberately
carries only a label, no price levels (see that phase's own report).
build_signal_for_buy constructs that Signal using the IDENTICAL
ATR-based stop/target convention strategy.baseline.TrendMomentumBaseline
already established (STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD) -- not a
second, competing risk methodology.

Still no order execution anywhere in this module: size_decision returns
a RiskDecision (existing type, existing meaning) for a caller to READ.
Converting an approved RiskDecision into an actual paper trade remains
the existing, unchanged paper/paper-live path.
"""

from market.context import MarketContext
from risk.account import Account
from risk.config import RiskConfig
from risk.contracts import RiskDecision
from risk.engine import RiskEngine
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal

from decision_engine.models import Decision, DecisionLabel


class SizingUnavailableError(Exception):
    """Raised when a decision cannot be turned into a sizeable Signal --
    e.g. a non-BUY label (only BUY implies a fresh entry to size), or a
    missing/non-positive ATR14 (degenerate, cannot size a stop). Mirrors
    TrendMomentumBaseline's own `if atr <= 0: return None` -- fail
    closed, never fabricate a stop distance."""


def build_signal_for_buy(decision: Decision, market_context: MarketContext) -> Signal:
    if decision.label != DecisionLabel.BUY:
        raise SizingUnavailableError(
            f"Cannot build a Signal for a {decision.label.value} decision -- only BUY implies a fresh entry to size."
        )
    if decision.symbol != market_context.symbol:
        raise SizingUnavailableError(
            f"Decision symbol {decision.symbol!r} does not match market context symbol {market_context.symbol!r}."
        )
    if market_context.atr_14 is None or market_context.atr_14 <= 0:
        raise SizingUnavailableError(f"No usable ATR14 for {decision.symbol} -- cannot size a stop.")

    reference_price = market_context.price
    stop_distance = market_context.atr_14 * STOP_ATR_MULTIPLIER
    stop_price = reference_price - stop_distance
    target_price = reference_price + stop_distance * TARGET_RISK_REWARD

    if stop_price <= 0:
        raise SizingUnavailableError(
            f"Computed stop price {stop_price:.2f} for {decision.symbol} is not positive "
            f"(reference {reference_price:.2f}, ATR14 {market_context.atr_14:.2f}) -- refusing to size a degenerate stop."
        )

    return Signal(
        symbol=decision.symbol,
        generated_at=market_context.as_of,
        side=Side.LONG,
        reference_price=reference_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_reward=TARGET_RISK_REWARD,
        strategy_name="decision_engine_buy_bridge",
        reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )


def size_decision(
    decision: Decision,
    *,
    market_context: MarketContext,
    account: Account,
    risk_config: RiskConfig | None = None,
) -> RiskDecision:
    signal = build_signal_for_buy(decision, market_context)
    engine = RiskEngine(risk_config or RiskConfig())
    return engine.evaluate(signal, account)
