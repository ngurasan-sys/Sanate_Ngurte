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


@pytest.mark.asyncio
async def test_concurrent_ensure_loaded_fetches_the_csv_once(master):
    """ensure_loaded() is now called from several entry points (feed connect,
    concurrent option-chain fetches). Without the double-checked lock, each
    concurrent caller would re-download the multi-megabyte CSV."""
    import asyncio

    async def slow_fetch():
        await asyncio.sleep(0.01)
        return SAMPLE_CSV

    master._fetch_csv_text = AsyncMock(side_effect=slow_fetch)

    await asyncio.gather(*(master.ensure_loaded() for _ in range(5)))

    assert master._fetch_csv_text.call_count == 1
    assert master.security_id_for_index("NIFTY") == "13"


@pytest.mark.asyncio
async def test_exchange_is_tracked_per_instrument(master):
    await master.ensure_loaded()
    assert master.exchange_for_index("NIFTY") == "NSE"
    assert master.exchange_for_index("SENSEX") == "BSE"  # SENSEX is BSE, not NSE
    assert master.exchange_for_option("NIFTY", "2026-10-30", 25000.0, "CE") == "NSE"
    assert master.exchange_for_security_id("51") == "BSE"
    assert master.exchange_for_security_id("1001") == "NSE"
    assert master.exchange_for_security_id("999999") is None


@pytest.mark.asyncio
async def test_underlying_reverse_lookup_from_security_id(master):
    await master.ensure_loaded()
    assert master.underlying_for_security_id("13") == "NIFTY"
    assert master.underlying_for_security_id("51") == "SENSEX"
    assert master.underlying_for_security_id("1001") is None  # an option, not an index
    assert master.is_index_security_id("25") is True
    assert master.is_index_security_id("1001") is False


def test_reverse_lookups_before_load_return_none_rather_than_raising(master):
    assert master.underlying_for_security_id("13") is None
    assert master.exchange_for_security_id("13") is None


@pytest.mark.asyncio
async def test_exchange_for_unknown_index_raises(master):
    await master.ensure_loaded()
    with pytest.raises(DhanInstrumentLookupError):
        master.exchange_for_index("FINNIFTY")
