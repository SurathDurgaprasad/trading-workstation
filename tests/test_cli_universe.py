"""Phase 29 -- `main.py universe` CLI. No real network in the unit suite:
DhanInstrumentMap.download is replaced with a fixture-backed fake."""

import io

import pandas as pd
import pytest

from main import parse_args, run_universe_command

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
"""


def test_universe_subcommand_defaults():
    args = parse_args(["universe", "--symbols", "AAPL,RELIANCE.NS"])
    assert args.command == "universe"
    assert args.symbols == "AAPL,RELIANCE.NS"
    assert args.with_dhan_ids is False
    assert args.refresh_instrument_map is False


def test_universe_requires_symbols_or_watchlist_file(capsys):
    args = parse_args(["universe"])
    with pytest.raises(SystemExit):
        run_universe_command(args)
    assert "one of --symbols or --watchlist-file" in capsys.readouterr().err


def test_universe_prints_exchange_for_each_symbol(capsys):
    args = parse_args(["universe", "--symbols", "AAPL,RELIANCE.NS,TCS.BO"])
    run_universe_command(args)

    output = capsys.readouterr().out
    assert "AAPL           OTHER" in output
    assert "RELIANCE.NS    NSE" in output
    assert "TCS.BO         BSE" in output
    assert "n/a" in output  # no --with-dhan-ids -- Dhan column shown as not-applicable


def test_universe_with_watchlist_file(tmp_path, capsys):
    path = tmp_path / "list.yaml"
    path.write_text("market_universe:\n  mode: watchlist\n  symbols:\n    - RELIANCE.NS\n    - INFY.NS\n")
    args = parse_args(["universe", "--watchlist-file", str(path)])
    run_universe_command(args)

    output = capsys.readouterr().out
    assert "watchlist (2 symbols)" in output
    assert "RELIANCE.NS" in output and "INFY.NS" in output


def test_a_malformed_watchlist_file_produces_a_clean_cli_error_not_a_traceback(tmp_path, capsys, monkeypatch):
    """Autonomous hardening cycle 13: the most serious real defect found
    this cycle -- `symbols: RELIANCE.NS` (a bare scalar, a plausible
    YAML typo for a one-item list) previously passed silently through
    `list("RELIANCE.NS")`, producing single-letter garbage tickers with
    NO error at all. Now raises a clear ValueError (already in main.py's
    _CONTROLLED_ERRORS, so no main.py change was needed this cycle,
    unlike cycle 12's SchedulerConfigurationError) -- proven end to end
    through a real main.main() invocation."""
    import main as main_module

    path = tmp_path / "bad_list.yaml"
    path.write_text("market_universe:\n  mode: watchlist\n  symbols: RELIANCE.NS\n")
    monkeypatch.setattr("sys.argv", ["main.py", "universe", "--watchlist-file", str(path)])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Universe failed" in err
    assert "must be a list" in err
    assert "Traceback" not in err


def test_universe_with_dhan_ids_resolves_known_symbols(monkeypatch, capsys):
    import live.dhan.instruments as instruments_module

    fake_map = instruments_module.DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))
    monkeypatch.setattr(instruments_module.DhanInstrumentMap, "download", classmethod(lambda cls, **kwargs: fake_map))

    args = parse_args(["universe", "--symbols", "RELIANCE.NS,AAPL", "--with-dhan-ids"])
    run_universe_command(args)

    output = capsys.readouterr().out
    assert "2885" in output
    assert "Reliance Industries" in output
    assert "not found" in output  # AAPL has no Dhan mapping


def test_universe_with_dhan_ids_passes_through_refresh_flag(monkeypatch):
    import live.dhan.instruments as instruments_module

    calls = {}

    def _fake_download(cls, **kwargs):
        calls.update(kwargs)
        return instruments_module.DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))

    monkeypatch.setattr(instruments_module.DhanInstrumentMap, "download", classmethod(_fake_download))

    args = parse_args(["universe", "--symbols", "RELIANCE.NS", "--with-dhan-ids", "--refresh-instrument-map"])
    run_universe_command(args)

    assert calls.get("force") is True
