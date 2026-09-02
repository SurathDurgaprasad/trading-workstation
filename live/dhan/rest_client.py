"""Phase 15 §14 — read-only Dhan REST access: funds, positions, holdings.
Every method here is a GET; none can mutate the real account. Field names
are transcribed VERBATIM from the current official docs
(dhanhq.co/docs/v2/portfolio/, dhanhq.co/docs/v2/funds/, read directly on
2026-09-01), including Dhan's own typo ("availabelBalance") -- not
"corrected," so a real response round-trips exactly.
"""

from dataclasses import dataclass
from typing import Callable

from live.dhan.config import DHAN_REST_BASE_URL, DhanCredentials


class DhanRestError(RuntimeError):
    """A Dhan REST call returned a non-2xx status or an unparseable body.
    Carries the HTTP status code so callers can distinguish, e.g., an
    expired token (DH-901/807) from a transient server error (908)."""

    def __init__(self, message: str, *, status_code: int | None = None, body: dict | list | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class DhanFundLimit:
    dhan_client_id: str
    available_balance: float
    sod_limit: float
    collateral_amount: float
    receivable_amount: float
    utilized_amount: float
    blocked_payout_amount: float
    withdrawable_balance: float

    @classmethod
    def from_api(cls, data: dict) -> "DhanFundLimit":
        return cls(
            dhan_client_id=data["dhanClientId"], available_balance=data["availabelBalance"], sod_limit=data["sodLimit"],
            collateral_amount=data["collateralAmount"], receivable_amount=data["receiveableAmount"], utilized_amount=data["utilizedAmount"],
            blocked_payout_amount=data["blockedPayoutAmount"], withdrawable_balance=data["withdrawableBalance"],
        )


@dataclass(frozen=True)
class DhanPosition:
    trading_symbol: str
    security_id: str
    position_type: str  # LONG | SHORT | CLOSED
    exchange_segment: str
    product_type: str
    net_quantity: int
    buy_average: float
    sell_average: float
    realized_profit: float
    unrealized_profit: float

    @classmethod
    def from_api(cls, data: dict) -> "DhanPosition":
        return cls(
            trading_symbol=data["tradingSymbol"], security_id=data["securityId"], position_type=data["positionType"],
            exchange_segment=data["exchangeSegment"], product_type=data["productType"], net_quantity=data["netQty"],
            buy_average=data["buyAvg"], sell_average=data["sellAvg"], realized_profit=data["realizedProfit"], unrealized_profit=data["unrealizedProfit"],
        )


@dataclass(frozen=True)
class DhanHolding:
    trading_symbol: str
    security_id: str
    isin: str
    total_quantity: int
    available_quantity: int
    average_cost_price: float

    @classmethod
    def from_api(cls, data: dict) -> "DhanHolding":
        return cls(
            trading_symbol=data["tradingSymbol"], security_id=data["securityId"], isin=data["isin"], total_quantity=data["totalQty"],
            available_quantity=data["availableQty"], average_cost_price=data["avgCostPrice"],
        )


# HttpGet's shape: (path, headers) -> (status_code, json_body). Kept this
# narrow (not a full requests.Response) so tests can inject a trivial fake
# without needing the `requests` library themselves.
HttpGet = Callable[[str, dict], tuple[int, dict | list]]


def _default_http_get(url: str, headers: dict) -> tuple[int, dict | list]:
    import requests

    response = requests.get(url, headers=headers, timeout=10)
    try:
        body = response.json()
    except ValueError:
        body = {}
    return response.status_code, body


@dataclass
class DhanRestClient:
    credentials: DhanCredentials
    http_get: HttpGet = _default_http_get
    base_url: str = DHAN_REST_BASE_URL

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "access-token": self.credentials.access_token}

    def _get(self, path: str):
        status_code, body = self.http_get(f"{self.base_url}{path}", self._headers())
        if status_code < 200 or status_code >= 300:
            raise DhanRestError(f"Dhan REST GET {path} returned HTTP {status_code}: {body}", status_code=status_code, body=body)
        return body

    def get_fund_limit(self) -> DhanFundLimit:
        return DhanFundLimit.from_api(self._get("/fundlimit"))

    def get_positions(self) -> list[DhanPosition]:
        return [DhanPosition.from_api(row) for row in self._get("/positions")]

    def get_holdings(self) -> list[DhanHolding]:
        # Phase 16 (VERIFIED against a real account, 2026-09-02): unlike
        # /positions, a real Dhan account with zero holdings makes /holdings
        # respond HTTP 500 with {"errorCode": "DH-1111", "errorMessage": "No
        # holdings available"} instead of 200 + []. This is NOT in the
        # documented Trading API (DH-901..910) or Data API (800..814) error
        # tables at dhanhq.co/docs/v2/annexure/ as of that date -- observed
        # live behavior, not a documented contract. Treated as "zero
        # holdings", not a failure; any other error still raises normally.
        try:
            body = self._get("/holdings")
        except DhanRestError as exc:
            if exc.status_code == 500 and isinstance(exc.body, dict) and exc.body.get("errorCode") == "DH-1111":
                return []
            raise
        return [DhanHolding.from_api(row) for row in body]
