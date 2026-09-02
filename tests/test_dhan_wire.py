"""Phase 15 §23 unit tests: DhanHQ v2 live-feed wire-format parsing. Every
byte sequence here is hand-built to match the documented format exactly
(live/dhan/wire.py's own docstring cites the source) -- no network, no
credentials, nothing environment-dependent.
"""
import struct

import pytest

from live.dhan.wire import (
    DhanDisconnectPacket,
    DhanFeedRequestCode,
    DhanFeedResponseCode,
    DhanFullPacket,
    DhanOpenInterestPacket,
    DhanPrevClosePacket,
    DhanQuotePacket,
    DhanTickerPacket,
    DhanWireFormatError,
    build_disconnect_message,
    build_feed_url,
    build_subscribe_message,
    parse_header,
    parse_packet,
)


def _header(response_code: int, payload_length: int = 0, segment_byte: int = 1, security_id: int = 2885) -> bytes:
    return struct.pack("<BhBi", response_code, payload_length, segment_byte, security_id)


def test_parse_header_reads_all_four_fields():
    header = parse_header(_header(DhanFeedResponseCode.TICKER, payload_length=16, segment_byte=1, security_id=2885))
    assert header.response_code == DhanFeedResponseCode.TICKER
    assert header.payload_length == 16
    assert header.exchange_segment == "NSE_EQ"
    assert header.security_id == 2885


def test_parse_header_rejects_a_packet_shorter_than_8_bytes():
    with pytest.raises(DhanWireFormatError):
        parse_header(b"\x02\x00\x00\x01\x00\x00")


def test_parse_header_rejects_an_unrecognized_exchange_segment_byte():
    with pytest.raises(DhanWireFormatError):
        parse_header(_header(DhanFeedResponseCode.TICKER, segment_byte=99))


def test_parse_ticker_packet():
    body = struct.pack("<fi", 1428.50, 1735689600)
    packet = parse_packet(_header(DhanFeedResponseCode.TICKER, security_id=2885) + body)
    assert isinstance(packet, DhanTickerPacket)
    assert packet.last_traded_price == pytest.approx(1428.50)
    assert packet.last_trade_time_epoch == 1735689600
    assert packet.header.security_id == 2885


def test_parse_prev_close_packet():
    body = struct.pack("<fi", 1400.00, 0)
    packet = parse_packet(_header(DhanFeedResponseCode.PREV_CLOSE) + body)
    assert isinstance(packet, DhanPrevClosePacket)
    assert packet.previous_close == pytest.approx(1400.00)


def test_parse_quote_packet_all_fields():
    body = struct.pack(
        "<fhifiiiffff",
        1428.50, 10, 1735689600, 1420.0, 100000, 40000, 60000, 1400.0, 0.0, 1450.0, 1390.0,
    )
    packet = parse_packet(_header(DhanFeedResponseCode.QUOTE) + body)
    assert isinstance(packet, DhanQuotePacket)
    assert packet.last_traded_price == pytest.approx(1428.50)
    assert packet.last_traded_quantity == 10
    assert packet.last_trade_time_epoch == 1735689600
    assert packet.average_trade_price == pytest.approx(1420.0)
    assert packet.volume == 100000
    assert packet.total_sell_quantity == 40000
    assert packet.total_buy_quantity == 60000
    assert packet.day_open == pytest.approx(1400.0)
    assert packet.day_close == pytest.approx(0.0)
    assert packet.day_high == pytest.approx(1450.0)
    assert packet.day_low == pytest.approx(1390.0)


def test_parse_oi_packet():
    body = struct.pack("<i", 12345)
    packet = parse_packet(_header(DhanFeedResponseCode.OI) + body)
    assert isinstance(packet, DhanOpenInterestPacket)
    assert packet.open_interest == 12345


def test_parse_full_packet_with_five_depth_levels():
    prefix = struct.pack(
        "<fhifiiiiiiffff",
        1428.50, 10, 1735689600, 1420.0, 100000, 40000, 60000, 0, 0, 0, 1400.0, 0.0, 1450.0, 1390.0,
    )
    depth = b"".join(
        struct.pack("<iihhff", 100 + i, 200 + i, 3, 4, 1427.0 - i, 1429.0 + i)
        for i in range(5)
    )
    packet = parse_packet(_header(DhanFeedResponseCode.FULL) + prefix + depth)
    assert isinstance(packet, DhanFullPacket)
    assert packet.last_traded_price == pytest.approx(1428.50)
    assert len(packet.depth) == 5
    assert packet.depth[0].bid_quantity == 100
    assert packet.depth[0].ask_quantity == 200
    assert packet.depth[0].bid_orders == 3
    assert packet.depth[0].ask_orders == 4
    assert packet.depth[4].bid_price == pytest.approx(1427.0 - 4)


def test_parse_disconnect_packet():
    body = struct.pack("<h", 805)
    packet = parse_packet(_header(DhanFeedResponseCode.DISCONNECT) + body)
    assert isinstance(packet, DhanDisconnectPacket)
    assert packet.reason_code == 805


def test_parse_packet_rejects_a_truncated_body():
    header = _header(DhanFeedResponseCode.TICKER)
    with pytest.raises(DhanWireFormatError):
        parse_packet(header + b"\x00\x00")  # only 2 of the required 8 body bytes


def test_parse_packet_rejects_an_unrecognized_response_code():
    with pytest.raises(DhanWireFormatError):
        parse_packet(_header(response_code=99) + b"\x00" * 8)


def test_build_feed_url_matches_documented_query_params():
    url = build_feed_url(client_id="1000000001", access_token="abc.def.ghi")
    assert url == "wss://api-feed.dhan.co?version=2&token=abc.def.ghi&clientId=1000000001&authType=2"


def test_build_subscribe_message_shape():
    message = build_subscribe_message(
        request_code=DhanFeedRequestCode.SUBSCRIBE_TICKER,
        instruments=[("NSE_EQ", "2885"), ("BSE_EQ", "532540")],
    )
    assert message == {
        "RequestCode": 15,
        "InstrumentCount": 2,
        "InstrumentList": [
            {"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"},
            {"ExchangeSegment": "BSE_EQ", "SecurityId": "532540"},
        ],
    }


def test_build_subscribe_message_rejects_more_than_100_instruments():
    with pytest.raises(ValueError):
        build_subscribe_message(request_code=DhanFeedRequestCode.SUBSCRIBE_TICKER, instruments=[("NSE_EQ", str(i)) for i in range(101)])


def test_build_disconnect_message():
    assert build_disconnect_message() == {"RequestCode": 12}
