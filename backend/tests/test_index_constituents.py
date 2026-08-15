import pytest

from backend.app.market_data.index_constituents import (
    BANKNIFTY_TOP7,
    NIFTY50_TOP10,
    get_constituents,
    total_weight_covered,
)


def test_nifty_has_exactly_10_constituents():
    assert len(NIFTY50_TOP10) == 10


def test_banknifty_has_exactly_7_constituents():
    assert len(BANKNIFTY_TOP7) == 7


@pytest.mark.parametrize("basket", [NIFTY50_TOP10, BANKNIFTY_TOP7])
def test_no_duplicate_symbols_within_a_basket(basket):
    symbols = [c.symbol for c in basket]
    assert len(symbols) == len(set(symbols))


@pytest.mark.parametrize("basket", [NIFTY50_TOP10, BANKNIFTY_TOP7])
def test_weights_are_sane_fractions(basket):
    for c in basket:
        assert 0.0 < c.weight < 1.0


@pytest.mark.parametrize("basket", [NIFTY50_TOP10, BANKNIFTY_TOP7])
def test_weights_are_sorted_descending(basket):
    # Both source pages list constituents ranked by weight — catches a
    # transcription slip (wrong row copied) rather than a real reordering.
    weights = [c.weight for c in basket]
    assert weights == sorted(weights, reverse=True)


def test_nifty_top10_covers_less_than_full_index():
    # 10 of 50 names, long-tail index -> well under 100%, but a large
    # chunk given cap-weighting.
    assert 0.3 < total_weight_covered("NIFTY") < 0.7


def test_banknifty_top7_covers_most_of_the_index():
    # Only ~12-14 constituents total and heavily concentrated in the top 3.
    assert total_weight_covered("BANKNIFTY") > 0.75


def test_get_constituents_unknown_index_raises():
    with pytest.raises(KeyError):
        get_constituents("FINNIFTY")


@pytest.mark.parametrize("basket", [NIFTY50_TOP10, BANKNIFTY_TOP7])
def test_every_constituent_has_a_sector(basket):
    for c in basket:
        assert c.sector


def test_nifty_top10_spans_multiple_sectors():
    sectors = {c.sector for c in NIFTY50_TOP10}
    assert len(sectors) >= 5


def test_banknifty_top7_is_entirely_financial_services():
    # It's a sector index by construction — every constituent must land
    # in the same sector, or the classification data is wrong.
    sectors = {c.sector for c in BANKNIFTY_TOP7}
    assert sectors == {"Financial Services"}


def test_hdfc_icici_sbi_appear_in_both_baskets():
    # Sanity check on the data itself: BANKNIFTY's top names are also
    # NIFTY heavyweights (financials dominate both), so overlap is
    # expected, not a bug.
    nifty_symbols = {c.symbol for c in NIFTY50_TOP10}
    banknifty_symbols = {c.symbol for c in BANKNIFTY_TOP7}
    assert {"HDFCBANK", "ICICIBANK", "SBIN"} <= (nifty_symbols & banknifty_symbols)
