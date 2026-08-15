from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS


def test_index_instrument_keys():
    assert INDEX_INSTRUMENT_KEYS == {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
    }
