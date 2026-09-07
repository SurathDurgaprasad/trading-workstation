"""EXECUTION SAFETY mission, Part 4 -- unit coverage for
market_intelligence/corporate_actions.py, using the SAME fake-yfinance-
Ticker pattern tests/test_research_news.py already established (no
network, real pandas Series shapes so .tail()/.items() are exercised for
real, not mocked away)."""
from datetime import date

import pandas as pd
import pytest

from market_intelligence.corporate_actions import CorporateActionKind, YahooCorporateActionsProvider
from research.errors import ResearchDataError


def _dividends(pairs: list[tuple[str, float]]) -> pd.Series:
    if not pairs:
        return pd.Series(dtype="float64")
    index = pd.DatetimeIndex([d for d, _ in pairs], tz="Asia/Kolkata")
    return pd.Series([v for _, v in pairs], index=index)


def _splits(pairs: list[tuple[str, float]]) -> pd.Series:
    return _dividends(pairs)  # same shape (DatetimeIndex -> float)


def _install_fake_ticker(monkeypatch, *, dividends=None, splits=None, calendar=None, raise_error=None):
    import yfinance

    class _FakeTicker:
        def __init__(self, symbol):
            if raise_error is not None:
                raise raise_error
            self.dividends = dividends if dividends is not None else _dividends([])
            self.splits = splits if splits is not None else _splits([])
            self.calendar = calendar or {}

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)


def test_fetch_corporate_actions_parses_real_shaped_dividends_and_splits(monkeypatch):
    _install_fake_ticker(
        monkeypatch,
        dividends=_dividends([("2025-08-14", 5.5), ("2026-06-05", 6.0)]),
        splits=_splits([("2024-10-28", 2.0)]),
        calendar={"Earnings Date": [date(2026, 10, 16)]},
    )

    snapshot = YahooCorporateActionsProvider().fetch_corporate_actions("RELIANCE.NS")

    assert snapshot.status == "AVAILABLE"
    assert snapshot.symbol == "RELIANCE.NS"
    kinds = {a.kind for a in snapshot.actions}
    assert kinds == {CorporateActionKind.DIVIDEND, CorporateActionKind.SPLIT, CorporateActionKind.EARNINGS_ESTIMATE}
    dividend = next(a for a in snapshot.actions if a.kind == CorporateActionKind.DIVIDEND and a.event_date == date(2026, 6, 5))
    assert "6.00" in dividend.detail
    earnings = next(a for a in snapshot.actions if a.kind == CorporateActionKind.EARNINGS_ESTIMATE)
    assert earnings.event_date == date(2026, 10, 16)
    assert "unconfirmed" in earnings.detail


def test_fetch_corporate_actions_respects_history_limits(monkeypatch):
    _install_fake_ticker(
        monkeypatch,
        dividends=_dividends([("2023-01-01", 1.0), ("2024-01-01", 2.0), ("2025-01-01", 3.0), ("2026-01-01", 4.0)]),
    )

    snapshot = YahooCorporateActionsProvider().fetch_corporate_actions("AAPL", dividend_history_limit=2)

    dividends = [a for a in snapshot.actions if a.kind == CorporateActionKind.DIVIDEND]
    assert len(dividends) == 2
    assert {a.event_date for a in dividends} == {date(2025, 1, 1), date(2026, 1, 1)}  # most recent, per .tail()


def test_fetch_corporate_actions_empty_result_is_available_not_unavailable(monkeypatch):
    """Genuinely no dividends/splits/earnings estimate is a REAL, valid
    outcome for some symbols -- status stays AVAILABLE (the fetch itself
    succeeded) with an empty actions tuple, never fabricated data."""
    _install_fake_ticker(monkeypatch)  # all empty defaults

    snapshot = YahooCorporateActionsProvider().fetch_corporate_actions("SOMEQUIETSTOCK.NS")

    assert snapshot.status == "AVAILABLE"
    assert snapshot.actions == ()


def test_fetch_corporate_actions_marks_unavailable_on_a_real_fetch_failure(monkeypatch):
    _install_fake_ticker(monkeypatch, raise_error=RuntimeError("simulated outage"))

    snapshot = YahooCorporateActionsProvider().fetch_corporate_actions("AAPL")

    assert snapshot.status == "UNAVAILABLE"
    assert "simulated outage" in snapshot.unavailable_reason
    assert snapshot.actions == ()


def test_fetch_corporate_actions_rejects_an_empty_symbol():
    with pytest.raises(ResearchDataError):
        YahooCorporateActionsProvider().fetch_corporate_actions("   ")


def test_fetch_corporate_actions_actions_are_sorted_by_event_date(monkeypatch):
    _install_fake_ticker(
        monkeypatch,
        dividends=_dividends([("2026-06-05", 6.0)]),
        splits=_splits([("2024-10-28", 2.0)]),
        calendar={"Earnings Date": [date(2026, 10, 16)]},
    )

    snapshot = YahooCorporateActionsProvider().fetch_corporate_actions("RELIANCE.NS")

    event_dates = [a.event_date for a in snapshot.actions]
    assert event_dates == sorted(event_dates)
