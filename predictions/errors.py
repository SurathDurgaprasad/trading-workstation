class PredictionUnavailableError(Exception):
    """Raised when a Decision cannot become a trackable PredictionRecord --
    e.g. a non-BUY label (only BUY has concrete price levels to monitor),
    or a symbol mismatch between the Decision and the Signal it was sized
    into. Mirrors risk.sizing.SizingUnavailableError's role and posture
    exactly -- fail closed, never fabricate a prediction with no real
    price levels behind it."""
