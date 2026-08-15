import pytest

from backend.app.market_data.lot_sizes import LOT_SIZES, get_lot_size


def test_get_lot_size_known_underlyings():
    assert get_lot_size("NIFTY") == 65
    assert get_lot_size("BANKNIFTY") == 30
    assert get_lot_size("SENSEX") == 20


def test_get_lot_size_unknown_underlying_raises_keyerror():
    with pytest.raises(KeyError):
        get_lot_size("FINNIFTY")


def test_lot_sizes_are_positive_integers():
    for symbol, size in LOT_SIZES.items():
        assert isinstance(size, int)
        assert size > 0
