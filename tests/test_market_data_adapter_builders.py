"""Construction-only tests for the adapter builder functions -- proves
they wire the EXISTING, unmodified MockMarketDataSource/DhanMarketDataSource
correctly without ever making a real network call. Real Dhan connectivity
itself is Phase 16's territory (tests/test_dhan_market_data_source.py),
not re-tested here.
"""

import io

import pandas as pd
import pytest

from live.dhan.config import DhanCredentials
from live.dhan.instruments import DhanInstrumentMap
from live.dhan.market_data_source import DhanMarketDataSource
from live.mock_source import MockMarketDataSource
from market_data.adapters._streaming import StreamingSnapshotAdapter
from market_data.adapters.dhan import build_dhan_adapter
from market_data.adapters.mock import build_mock_adapter
from tests.conftest import AAPL_CACHE_PATH

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
"""


@pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
def test_build_mock_adapter_wraps_a_real_mock_market_data_source():
    adapter = build_mock_adapter("AAPL", interval="1d", period="1y")
    assert isinstance(adapter, StreamingSnapshotAdapter)
    assert isinstance(adapter._source, MockMarketDataSource)


def test_build_dhan_adapter_wraps_a_dhan_market_data_source_without_connecting():
    """Fake, never-used credentials -- DhanMarketDataSource does not
    connect at construction time (only subscribe() does, and that only
    happens lazily on the adapter's first get_snapshot() call), so no
    network call occurs here."""
    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token-never-used")
    instrument_map = DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))

    adapter = build_dhan_adapter(credentials=credentials, instrument_map=instrument_map, interval="1m", max_reconnect_attempts=0)

    assert isinstance(adapter, StreamingSnapshotAdapter)
    assert isinstance(adapter._source, DhanMarketDataSource)
    assert adapter._source.max_reconnect_attempts == 0  # source_kwargs passed through unchanged
