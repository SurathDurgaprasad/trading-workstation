from datetime import datetime, timedelta

import pytest

from live.contracts import FeedDisconnectedError
from live.mock_source import MockMarketDataSource, MockScriptEvent, make_mock_bar
from market.data_provider import DataSource, DataStatus
from tests.conftest import AAPL_CACHE_PATH


def _bar(day, **overrides):
    base = dict(timestamp=datetime(2026, 1, day, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    base.update(overrides)
    return make_mock_bar(**base)


def test_bars_are_tagged_mock_and_simulated():
    source = MockMarketDataSource([MockScriptEvent.bar_event("TEST", _bar(1))])
    source.subscribe(["TEST"], "1d")
    event = source.next_bar()
    assert event.symbol == "TEST"
    assert event.bar.source == DataSource.MOCK
    assert event.bar.status == DataStatus.SIMULATED


def test_bars_arrive_in_deterministic_order():
    script = [MockScriptEvent.bar_event("TEST", _bar(d)) for d in (1, 2, 3)]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    timestamps = []
    while (event := source.next_bar()) is not None:
        timestamps.append(event.bar.timestamp)
    assert timestamps == [datetime(2026, 1, 1, 9, 15), datetime(2026, 1, 2, 9, 15), datetime(2026, 1, 3, 9, 15)]


def test_script_exhaustion_returns_none_not_an_error():
    source = MockMarketDataSource([MockScriptEvent.bar_event("TEST", _bar(1))])
    source.subscribe(["TEST"], "1d")
    source.next_bar()
    assert source.next_bar() is None
    assert source.next_bar() is None  # repeated calls after exhaustion stay None, not an error


def test_duplicate_bar_can_be_scripted_and_is_delivered_twice():
    """The mock source itself doesn't deduplicate -- that's
    PaperTradingEngine.process_bar's job (Phase 7A), tested end to end in
    test_live_pipeline.py. Here we only confirm the mock faithfully
    delivers exactly what the script says, including an intentional dup."""
    same_bar = _bar(1)
    script = [MockScriptEvent.bar_event("TEST", same_bar), MockScriptEvent.bar_event("TEST", same_bar)]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    first = source.next_bar()
    second = source.next_bar()
    assert first.bar.timestamp == second.bar.timestamp == datetime(2026, 1, 1, 9, 15)


def test_out_of_order_bar_can_be_scripted():
    script = [MockScriptEvent.bar_event("TEST", _bar(5)), MockScriptEvent.bar_event("TEST", _bar(3))]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    first = source.next_bar()
    second = source.next_bar()
    assert first.bar.timestamp > second.bar.timestamp  # the mock delivers exactly this order; downstream must reject it


def test_missing_bar_gap_is_just_an_absent_script_entry():
    # Day 2 is simply never scripted -- a gap.
    script = [MockScriptEvent.bar_event("TEST", _bar(1)), MockScriptEvent.bar_event("TEST", _bar(3))]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    first = source.next_bar()
    second = source.next_bar()
    assert (second.bar.timestamp - first.bar.timestamp) == timedelta(days=2)


def test_delayed_bar_has_received_at_far_after_its_own_timestamp():
    bar_ts = datetime(2026, 1, 1, 9, 15)
    delivery_time = bar_ts + timedelta(minutes=8)  # delivered 8 minutes late
    source = MockMarketDataSource([MockScriptEvent.bar_event("TEST", _bar(1))], clock=lambda: delivery_time)
    source.subscribe(["TEST"], "1m")
    event = source.next_bar()
    assert event.bar.received_at == delivery_time
    assert (event.bar.received_at - event.bar.timestamp) == timedelta(minutes=8)


def test_bar_during_disconnect_is_lost_and_raises():
    """A bar that would have arrived during an outage is LOST, not queued
    -- matching a real streaming feed, which does not replay missed ticks
    after an outage. The exception is the signal; there is nothing to
    redeliver."""
    script = [MockScriptEvent.disconnect(), MockScriptEvent.bar_event("TEST", _bar(1))]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")

    with pytest.raises(FeedDisconnectedError):
        source.next_bar()  # this call is what actually processes the DISCONNECT event
    assert source.is_connected() is False


def test_multiple_bars_during_extended_disconnect_each_raise_in_turn():
    script = [
        MockScriptEvent.disconnect(),
        MockScriptEvent.bar_event("TEST", _bar(1)),
        MockScriptEvent.bar_event("TEST", _bar(2)),
        MockScriptEvent.reconnect(),
        MockScriptEvent.bar_event("TEST", _bar(3)),
    ]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")

    with pytest.raises(FeedDisconnectedError):
        source.next_bar()  # bar 1 lost
    with pytest.raises(FeedDisconnectedError):
        source.next_bar()  # bar 2 lost

    event = source.next_bar()  # reconnected -- bar 3 delivered normally
    assert event is not None
    assert event.bar.timestamp == datetime(2026, 1, 3, 9, 15)
    assert source.is_connected() is True


def test_bar_scripted_after_reconnect_is_delivered_normally():
    script = [MockScriptEvent.disconnect(), MockScriptEvent.reconnect(), MockScriptEvent.bar_event("TEST", _bar(1))]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    event = source.next_bar()
    assert event is not None
    assert event.bar.timestamp == datetime(2026, 1, 1, 9, 15)
    assert source.is_connected() is True


def test_unsubscribed_symbol_bars_are_skipped_not_delivered():
    script = [MockScriptEvent.bar_event("OTHER", _bar(1)), MockScriptEvent.bar_event("TEST", _bar(2))]
    source = MockMarketDataSource(script)
    source.subscribe(["TEST"], "1d")
    event = source.next_bar()
    assert event.symbol == "TEST"


def test_close_prevents_further_reads():
    source = MockMarketDataSource([MockScriptEvent.bar_event("TEST", _bar(1))])
    source.subscribe(["TEST"], "1d")
    source.close()
    with pytest.raises(RuntimeError):
        source.next_bar()


@pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
def test_from_cached_history_replays_real_data_tagged_as_mock():
    source = MockMarketDataSource.from_cached_history("AAPL", interval="1d", period="5y")
    event = source.next_bar()
    assert event.symbol == "AAPL"
    assert event.bar.source == DataSource.MOCK
    assert event.bar.status == DataStatus.SIMULATED
    assert event.bar.close > 0
