class ResearchDataError(Exception):
    """Raised when news/sector research data cannot be fetched or parsed.
    Matches market.data_provider.MarketDataError's role for this package --
    a known, controlled failure mode, not an unexpected bug."""
