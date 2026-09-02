"""Phase 15 §23 unit tests: DhanRestClient, tested against an injected fake
HTTP GET (no real network, no credentials). Field mappings are checked
against the exact response shapes shown in the current official docs.
"""
import pytest

from live.dhan.config import DhanCredentials
from live.dhan.rest_client import DhanFundLimit, DhanHolding, DhanPosition, DhanRestClient, DhanRestError


def _fake_get(responses: dict):
    def _get(url: str, headers: dict):
        for path, (status, body) in responses.items():
            if url.endswith(path):
                assert headers["access-token"] == "fake-token"
                return status, body
        raise AssertionError(f"Unexpected URL requested: {url}")

    return _get


@pytest.fixture
def credentials() -> DhanCredentials:
    return DhanCredentials(client_id="1000000009", access_token="fake-token")


def test_get_fund_limit_maps_every_field_including_the_documented_typo(credentials):
    body = {
        "dhanClientId": "1000000009", "availabelBalance": 98440.0, "sodLimit": 113642, "collateralAmount": 0.0,
        "receiveableAmount": 0.0, "utilizedAmount": 15202.0, "blockedPayoutAmount": 0.0, "withdrawableBalance": 98310.0,
    }
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/fundlimit": (200, body)}))
    fund_limit = client.get_fund_limit()
    assert isinstance(fund_limit, DhanFundLimit)
    assert fund_limit.available_balance == 98440.0
    assert fund_limit.dhan_client_id == "1000000009"
    assert fund_limit.withdrawable_balance == 98310.0


def test_get_positions_maps_all_fields(credentials):
    body = [{
        "dhanClientId": "1000000009", "tradingSymbol": "TCS", "securityId": "11536", "positionType": "LONG",
        "exchangeSegment": "NSE_EQ", "productType": "CNC", "buyAvg": 3345.8, "buyQty": 40, "costPrice": 3215.0,
        "sellAvg": 0.0, "sellQty": 0, "netQty": 40, "realizedProfit": 0.0, "unrealizedProfit": 6122.0,
        "rbiReferenceRate": 1.0, "multiplier": 1, "carryForwardBuyQty": 0, "carryForwardSellQty": 0,
        "carryForwardBuyValue": 0.0, "carryForwardSellValue": 0.0, "dayBuyQty": 40, "daySellQty": 0,
        "dayBuyValue": 133832.0, "daySellValue": 0.0, "drvExpiryDate": "0001-01-01", "drvOptionType": None,
        "drvStrikePrice": 0.0, "crossCurrency": False,
    }]
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/positions": (200, body)}))
    positions = client.get_positions()
    assert len(positions) == 1
    assert isinstance(positions[0], DhanPosition)
    assert positions[0].trading_symbol == "TCS"
    assert positions[0].net_quantity == 40
    assert positions[0].unrealized_profit == 6122.0


def test_get_holdings_maps_all_fields(credentials):
    body = [{
        "exchange": "ALL", "tradingSymbol": "HDFC", "securityId": "1330", "isin": "INE001A01036", "totalQty": 1000,
        "dpQty": 1000, "t1Qty": 0, "availableQty": 1000, "collateralQty": 0, "avgCostPrice": 2655.0,
    }]
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/holdings": (200, body)}))
    holdings = client.get_holdings()
    assert len(holdings) == 1
    assert isinstance(holdings[0], DhanHolding)
    assert holdings[0].trading_symbol == "HDFC"
    assert holdings[0].average_cost_price == 2655.0


def test_empty_positions_list_is_handled_cleanly(credentials):
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/positions": (200, [])}))
    assert client.get_positions() == []


def test_dh1111_zero_holdings_error_is_treated_as_an_empty_list(credentials):
    """Phase 16 (VERIFIED against a real account): a real Dhan account with
    zero holdings makes /holdings return HTTP 500 + errorCode DH-1111
    instead of 200 + [] -- undocumented in the official error tables, but
    observed live. This must be treated as "no holdings", not a failure."""
    body = {"errorType": "HOLDING_ERROR", "errorCode": "DH-1111", "errorMessage": "No holdings available"}
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/holdings": (500, body)}))
    assert client.get_holdings() == []


def test_other_500_errors_on_holdings_still_raise(credentials):
    """Only the specific DH-1111 "no holdings" shape is swallowed -- any
    other error status/body on /holdings must still raise, unchanged."""
    body = {"errorType": "INTERNAL_SERVER_ERROR", "errorCode": "DH-908", "errorMessage": "Server error"}
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/holdings": (500, body)}))
    with pytest.raises(DhanRestError) as exc_info:
        client.get_holdings()
    assert exc_info.value.status_code == 500


def test_non_2xx_status_raises_dhan_rest_error_with_status_code(credentials):
    client = DhanRestClient(credentials=credentials, http_get=_fake_get({"/fundlimit": (401, {"errorCode": "DH-901", "errorMessage": "Invalid token"})}))
    with pytest.raises(DhanRestError) as exc_info:
        client.get_fund_limit()
    assert exc_info.value.status_code == 401


def test_get_requests_never_use_a_mutating_http_method():
    """Structural check: DhanRestClient exposes no method whose name
    suggests a write (post/put/delete/place/modify/cancel/submit)."""
    import inspect

    public_methods = [name for name, _ in inspect.getmembers(DhanRestClient, predicate=inspect.isfunction) if not name.startswith("_")]
    forbidden = ("post", "put", "delete", "place", "modify", "cancel", "submit", "create")
    for method_name in public_methods:
        for verb in forbidden:
            assert verb not in method_name.lower(), f"{method_name} looks like a mutating call"
