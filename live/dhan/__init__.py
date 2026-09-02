"""Phase 15 — the real Dhan integration, isolated in its own package so the
rest of the codebase never imports anything Dhan-specific. Everything
outside live/dhan/ still only knows live.contracts.MarketDataSource,
live.broker.BrokerAdapter, and market.data_provider.OHLCVBar.

Nothing in this package can place a real order (see broker_adapter.py) --
that stays true regardless of what credentials are configured.
"""
