from strategy.baseline import TrendMomentumBaseline
from strategy.contracts import Strategy

# Exactly one entry, deliberately. This is a lookup, not a strategy factory —
# Phase 3 explicitly builds one baseline strategy, not a library of them.
_STRATEGIES: dict[str, type[Strategy]] = {
    TrendMomentumBaseline.name: TrendMomentumBaseline,
}


class UnknownStrategyError(ValueError):
    def __init__(self, name: str):
        self.name = name
        available = ", ".join(sorted(_STRATEGIES))
        super().__init__(f"Unknown strategy '{name}'. Available: {available}")


def get_strategy(name: str) -> Strategy:
    try:
        strategy_cls = _STRATEGIES[name]
    except KeyError:
        raise UnknownStrategyError(name) from None
    return strategy_cls()
