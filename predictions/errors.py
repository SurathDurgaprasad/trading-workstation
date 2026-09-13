from datetime import datetime


class PredictionUnavailableError(Exception):
    """Raised when a Decision cannot become a trackable PredictionRecord --
    e.g. a non-BUY label (only BUY has concrete price levels to monitor),
    or a symbol mismatch between the Decision and the Signal it was sized
    into. Mirrors risk.sizing.SizingUnavailableError's role and posture
    exactly -- fail closed, never fabricate a prediction with no real
    price levels behind it."""


class DuplicatePredictionError(Exception):
    """Final-product-hardening: raised by PredictionStore.save_prediction
    when a DB-level UNIQUE(symbol, entry_time) constraint (see
    predictions/store.py's own _migrate_entry_time_column_and_unique_index)
    rejects an insert -- a prediction already exists for this exact
    symbol+entry bar. This is the atomic guarantee
    has_prediction_for_entry's own check-then-insert cannot give on its
    own: two concurrent callers could both pass that check before either
    had inserted. Callers should generally check has_prediction_for_entry
    FIRST (cheaper, avoids the round-trip to the DB engine's own
    constraint machinery for the common case) and treat this as the rare,
    genuine race the check-then-insert pattern cannot close by itself."""

    def __init__(self, *, symbol: str, entry_time: datetime):
        self.symbol = symbol
        self.entry_time = entry_time
        super().__init__(f"A prediction for {symbol} at entry_time {entry_time.isoformat()} already exists.")


class DuplicateForecastError(Exception):
    """Same rationale as DuplicatePredictionError, for
    predictions/direction_forecast_store.py's DirectionForecastStore --
    see that store's _migrate_as_of_column_and_unique_index."""

    def __init__(self, *, symbol: str, as_of: datetime):
        self.symbol = symbol
        self.as_of = as_of
        super().__init__(f"A forecast for {symbol} at as_of {as_of.isoformat()} already exists.")
