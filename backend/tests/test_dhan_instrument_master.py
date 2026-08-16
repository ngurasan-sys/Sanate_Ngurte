import pytest
from unittest.mock import AsyncMock

from backend.app.core.dhan_instrument_master import (
    DhanInstrumentLookupError,
    DhanInstrumentMaster,
)

SAMPLE_CSV = (
    "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_TRADING_SYMBOL,"
    "SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_INSTRUMENT_NAME\n"
    "NSE,I,13,NIFTY 50,NIFTY,,,,INDEX\n"
    "NSE,I,25,NIFTY BANK,BANKNIFTY,,,,INDEX\n"
    "BSE,I,51,SENSEX,SENSEX,,,,INDEX\n"
    "NSE,D,1001,NIFTY-Oct2026-25000-CE,NIFTY 25000 CE,2026-10-30,25000,CE,OPTIDX\n"
    "NSE,D,1002,NIFTY-Oct2026-25000-PE,NIFTY 25000 PE,2026-10-30,25000,PE,OPTIDX\n"
)


@pytest.fixture
def master(monkeypatch):
    m = DhanInstrumentMaster()
    monkeypatch.setattr(m, "_fetch_csv_text", AsyncMock(return_value=SAMPLE_CSV))
    return m


@pytest.mark.asyncio
async def test_security_id_for_known_index(master):
    await master.ensure_loaded()
    assert master.security_id_for_index("NIFTY") == "13"
    assert master.security_id_for_index("SENSEX") == "51"


def test_security_id_for_index_before_load_raises(master):
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_index("NIFTY")


@pytest.mark.asyncio
async def test_security_id_for_unknown_index_raises(master):
    await master.ensure_loaded()
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_index("FINNIFTY")


@pytest.mark.asyncio
async def test_security_id_for_option_matches_expiry_strike_type(master):
    await master.ensure_loaded()
    assert master.security_id_for_option("NIFTY", "2026-10-30", 25000.0, "CE") == "1001"
    assert master.security_id_for_option("NIFTY", "2026-10-30", 25000.0, "PE") == "1002"


@pytest.mark.asyncio
async def test_security_id_for_option_no_match_raises(master):
    await master.ensure_loaded()
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_option("NIFTY", "2026-10-30", 99999.0, "CE")


@pytest.mark.asyncio
async def test_ensure_loaded_only_fetches_once(master):
    await master.ensure_loaded()
    await master.ensure_loaded()
    master._fetch_csv_text.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_forces_a_new_fetch(master):
    await master.ensure_loaded()
    await master.refresh()
    assert master._fetch_csv_text.call_count == 2
