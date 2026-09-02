"""Phase 15 §3/§5 — the exact DhanHQ v2 Live Market Feed wire format, read
directly from the current official docs on 2026-09-01 (docs.dhanhq.co /
dhanhq.co/docs/v2/live-market-feed, dhanhq.co/docs/v2/annexure — both are
JS-rendered SPAs, verified via direct browser rendering, not a static
fetch). Every offset/type below is transcribed from that page, not
inferred or copied from Phase 14's broker-comparison notes.

VERIFIED FROM CURRENT DHAN DOCUMENTATION (2026-09-01):
  - WebSocket URL: wss://api-feed.dhan.co?version=2&token=<token>&clientId=<id>&authType=2
  - Up to 5 connections/user, 5000 instruments/connection, 100 instruments/subscribe message
  - Server ping every 10s; client must respond within 40s or the connection is closed
  - All requests JSON, all responses binary, little-endian
  - Response header: 8 bytes -- [0]=response code, [1:3]=int16 payload length,
    [3]=exchange segment byte, [4:8]=int32 security ID
  - Ticker(2)/PrevClose(6): header + float32 + int32 = 16 bytes
  - Quote(4): header + float32 LTP + int16 LTQ + int32 LTT + float32 ATP +
    int32 Volume + int32 TotalSellQty + int32 TotalBuyQty + float32 DayOpen +
    float32 DayClose + float32 DayHigh + float32 DayLow = 50 bytes
  - OI(5): header + int32 = 12 bytes
  - Full(8): header + float32 LTP + int16 LTQ + int32 LTT + float32 ATP +
    int32 Volume + int32 SellQty + int32 BuyQty + int32 OI + int32 HighOI +
    int32 LowOI + float32 DayOpen/Close/High/Low + 5x20-byte depth = 162 bytes
  - Depth entry (20 bytes): int32 BidQty, int32 AskQty, int16 #BidOrders,
    int16 #AskOrders, float32 BidPrice, float32 AskPrice
  - Disconnect(50): header + int16 reason code = 10 bytes

REQUIRES CONFIRMATION: the Market Status packet (response code 7, listed in
the Annexure table) has NO documented byte layout on the live docs as of
this reading -- only its response code is given. This module does not
attempt to parse it; market_session.py derives session state from IST
wall-clock time instead (see that module's own docstring for why).
"""

import struct
from dataclasses import dataclass
from enum import IntEnum

# -- request codes (Annexure, VERIFIED) --------------------------------------


class DhanFeedRequestCode(IntEnum):
    CONNECT = 11
    DISCONNECT = 12
    SUBSCRIBE_TICKER = 15
    UNSUBSCRIBE_TICKER = 16
    SUBSCRIBE_QUOTE = 17
    UNSUBSCRIBE_QUOTE = 18
    SUBSCRIBE_FULL = 21
    UNSUBSCRIBE_FULL = 22
    SUBSCRIBE_DEPTH = 23
    UNSUBSCRIBE_DEPTH = 24


# -- response codes (Annexure, VERIFIED) --------------------------------------


class DhanFeedResponseCode(IntEnum):
    INDEX = 1
    TICKER = 2
    QUOTE = 4
    OI = 5
    PREV_CLOSE = 6
    MARKET_STATUS = 7
    FULL = 8
    DISCONNECT = 50


# -- exchange segment: JSON string name (requests) vs. wire byte (responses),
# both VERIFIED from the Annexure table --------------------------------------


class DhanExchangeSegment(str):
    """Not an Enum on purpose -- these are the exact strings the JSON
    subscribe request expects (InstrumentList.ExchangeSegment)."""

    IDX_I = "IDX_I"
    NSE_EQ = "NSE_EQ"
    NSE_FNO = "NSE_FNO"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_EQ = "BSE_EQ"
    MCX_COMM = "MCX_COMM"
    BSE_CURRENCY = "BSE_CURRENCY"
    BSE_FNO = "BSE_FNO"


_EXCHANGE_SEGMENT_BY_WIRE_BYTE: dict[int, str] = {
    0: DhanExchangeSegment.IDX_I,
    1: DhanExchangeSegment.NSE_EQ,
    2: DhanExchangeSegment.NSE_FNO,
    3: DhanExchangeSegment.NSE_CURRENCY,
    4: DhanExchangeSegment.BSE_EQ,
    5: DhanExchangeSegment.MCX_COMM,
    7: DhanExchangeSegment.BSE_CURRENCY,
    8: DhanExchangeSegment.BSE_FNO,
}

MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE = 100  # VERIFIED (docs: "upto 100 instruments in a single JSON message")

HEADER_SIZE = 8
_HEADER_STRUCT = struct.Struct("<BhBi")  # response code(1) + payload length(int16) + segment byte(1) + security id(int32)


class DhanWireFormatError(ValueError):
    """A response packet was too short, had an unrecognized response code,
    or otherwise didn't match the documented wire format. Raised rather
    than silently returning a partially-parsed/zeroed packet -- a
    corrupted market-data packet must never be treated as a valid price."""


@dataclass(frozen=True)
class DhanPacketHeader:
    response_code: int
    payload_length: int
    exchange_segment: str
    security_id: int


def parse_header(data: bytes) -> DhanPacketHeader:
    if len(data) < HEADER_SIZE:
        raise DhanWireFormatError(f"Packet too short for an 8-byte header: {len(data)} bytes.")
    response_code, payload_length, segment_byte, security_id = _HEADER_STRUCT.unpack_from(data, 0)
    segment = _EXCHANGE_SEGMENT_BY_WIRE_BYTE.get(segment_byte)
    if segment is None:
        raise DhanWireFormatError(f"Unrecognized exchange segment byte in packet header: {segment_byte}.")
    return DhanPacketHeader(response_code=response_code, payload_length=payload_length, exchange_segment=segment, security_id=security_id)


@dataclass(frozen=True)
class DhanTickerPacket:
    header: DhanPacketHeader
    last_traded_price: float
    last_trade_time_epoch: int


@dataclass(frozen=True)
class DhanPrevClosePacket:
    header: DhanPacketHeader
    previous_close: float
    previous_open_interest: int


@dataclass(frozen=True)
class DhanQuotePacket:
    header: DhanPacketHeader
    last_traded_price: float
    last_traded_quantity: int
    last_trade_time_epoch: int
    average_trade_price: float
    volume: int
    total_sell_quantity: int
    total_buy_quantity: int
    day_open: float
    day_close: float
    day_high: float
    day_low: float


@dataclass(frozen=True)
class DhanOpenInterestPacket:
    header: DhanPacketHeader
    open_interest: int


@dataclass(frozen=True)
class DhanDepthLevel:
    bid_quantity: int
    ask_quantity: int
    bid_orders: int
    ask_orders: int
    bid_price: float
    ask_price: float


@dataclass(frozen=True)
class DhanFullPacket:
    header: DhanPacketHeader
    last_traded_price: float
    last_traded_quantity: int
    last_trade_time_epoch: int
    average_trade_price: float
    volume: int
    total_sell_quantity: int
    total_buy_quantity: int
    open_interest: int
    day_open: float
    day_close: float
    day_high: float
    day_low: float
    depth: tuple[DhanDepthLevel, ...]


@dataclass(frozen=True)
class DhanDisconnectPacket:
    header: DhanPacketHeader
    reason_code: int


DhanPacket = DhanTickerPacket | DhanPrevClosePacket | DhanQuotePacket | DhanOpenInterestPacket | DhanFullPacket | DhanDisconnectPacket

_TICKER_BODY = struct.Struct("<fi")  # LTP float32, LTT int32
_QUOTE_BODY = struct.Struct("<fhifiiiffff")  # LTP, LTQ int16, LTT int32, ATP, Vol, SellQty, BuyQty, Open, Close, High, Low
_OI_BODY = struct.Struct("<i")
_FULL_BODY_PREFIX = struct.Struct("<fhifiiiiiiffff")  # LTP, LTQ, LTT, ATP, Vol, SellQty, BuyQty, OI, HighOI, LowOI, Open, Close, High, Low
_DEPTH_LEVEL = struct.Struct("<iihhff")  # BidQty, AskQty, #BidOrders, #AskOrders, BidPrice, AskPrice
_DISCONNECT_BODY = struct.Struct("<h")


def parse_packet(data: bytes) -> DhanPacket:
    """Dispatches on the header's response_code to the matching packet
    shape. Raises DhanWireFormatError for anything shorter than its
    documented size or an unrecognized response code -- a truncated or
    unexpected packet is never silently coerced into a valid-looking bar."""
    header = parse_header(data)
    body = data[HEADER_SIZE:]

    if header.response_code in (DhanFeedResponseCode.TICKER, DhanFeedResponseCode.PREV_CLOSE):
        if len(body) < _TICKER_BODY.size:
            raise DhanWireFormatError(f"Ticker/PrevClose body too short: {len(body)} bytes, need {_TICKER_BODY.size}.")
        value, second = _TICKER_BODY.unpack_from(body, 0)
        if header.response_code == DhanFeedResponseCode.TICKER:
            return DhanTickerPacket(header=header, last_traded_price=value, last_trade_time_epoch=second)
        return DhanPrevClosePacket(header=header, previous_close=value, previous_open_interest=second)

    if header.response_code == DhanFeedResponseCode.QUOTE:
        if len(body) < _QUOTE_BODY.size:
            raise DhanWireFormatError(f"Quote body too short: {len(body)} bytes, need {_QUOTE_BODY.size}.")
        ltp, ltq, ltt, atp, volume, sell_qty, buy_qty, day_open, day_close, day_high, day_low = _QUOTE_BODY.unpack_from(body, 0)
        return DhanQuotePacket(
            header=header, last_traded_price=ltp, last_traded_quantity=ltq, last_trade_time_epoch=ltt, average_trade_price=atp,
            volume=volume, total_sell_quantity=sell_qty, total_buy_quantity=buy_qty, day_open=day_open, day_close=day_close,
            day_high=day_high, day_low=day_low,
        )

    if header.response_code == DhanFeedResponseCode.OI:
        if len(body) < _OI_BODY.size:
            raise DhanWireFormatError(f"OI body too short: {len(body)} bytes, need {_OI_BODY.size}.")
        (oi,) = _OI_BODY.unpack_from(body, 0)
        return DhanOpenInterestPacket(header=header, open_interest=oi)

    if header.response_code == DhanFeedResponseCode.FULL:
        min_size = _FULL_BODY_PREFIX.size + 5 * _DEPTH_LEVEL.size
        if len(body) < min_size:
            raise DhanWireFormatError(f"Full body too short: {len(body)} bytes, need {min_size}.")
        ltp, ltq, ltt, atp, volume, sell_qty, buy_qty, oi, high_oi, low_oi, day_open, day_close, day_high, day_low = _FULL_BODY_PREFIX.unpack_from(body, 0)
        depth_offset = _FULL_BODY_PREFIX.size
        depth = tuple(
            DhanDepthLevel(*_DEPTH_LEVEL.unpack_from(body, depth_offset + i * _DEPTH_LEVEL.size))
            for i in range(5)
        )
        return DhanFullPacket(
            header=header, last_traded_price=ltp, last_traded_quantity=ltq, last_trade_time_epoch=ltt, average_trade_price=atp,
            volume=volume, total_sell_quantity=sell_qty, total_buy_quantity=buy_qty, open_interest=oi, day_open=day_open,
            day_close=day_close, day_high=day_high, day_low=day_low, depth=depth,
        )

    if header.response_code == DhanFeedResponseCode.DISCONNECT:
        if len(body) < _DISCONNECT_BODY.size:
            raise DhanWireFormatError(f"Disconnect body too short: {len(body)} bytes, need {_DISCONNECT_BODY.size}.")
        (reason_code,) = _DISCONNECT_BODY.unpack_from(body, 0)
        return DhanDisconnectPacket(header=header, reason_code=reason_code)

    raise DhanWireFormatError(f"Unrecognized or unhandled feed response code: {header.response_code}.")


# -- outbound JSON request builders (VERIFIED shape from the live docs) ------


def build_feed_url(*, client_id: str, access_token: str) -> str:
    from live.dhan.config import DHAN_FEED_WS_URL

    return f"{DHAN_FEED_WS_URL}?version=2&token={access_token}&clientId={client_id}&authType=2"


def build_subscribe_message(*, request_code: DhanFeedRequestCode, instruments: list[tuple[str, str]]) -> dict:
    """`instruments` is a list of (exchange_segment, security_id) pairs.
    Raises ValueError if more than 100 are given in one message -- the
    caller (DhanMarketDataSource) is responsible for chunking a larger
    subscription list into multiple calls, per the documented limit."""
    if len(instruments) > MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE:
        raise ValueError(f"At most {MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE} instruments per subscribe message (Dhan's documented limit); got {len(instruments)}.")
    return {
        "RequestCode": int(request_code),
        "InstrumentCount": len(instruments),
        "InstrumentList": [{"ExchangeSegment": segment, "SecurityId": security_id} for segment, security_id in instruments],
    }


def build_disconnect_message() -> dict:
    return {"RequestCode": int(DhanFeedRequestCode.DISCONNECT)}
