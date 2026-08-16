from datetime import datetime, timedelta, timezone

from backend.app.strategies.order_flow_absorption.option_selection import (
    OptionCandidate, extract_candidates_from_chain, select_best_option, validate_candidate,
)

NOW = datetime(2024, 10, 1, 10, 0, 0, tzinfo=timezone.utc)


def _leg(instrument_key, bid, ask, ltp, volume, oi, iv=0.15, delta=0.5):
    return {
        "instrument_key": instrument_key,
        "market_data": {"bid_price": bid, "ask_price": ask, "ltp": ltp, "volume": volume, "oi": oi},
        "option_greeks": {"iv": iv, "delta": delta, "gamma": 0.01, "theta": -1.2, "vega": 5.0},
    }


def _chain_entry(strike, ce_leg=None, pe_leg=None):
    entry = {"strike_price": strike}
    if ce_leg:
        entry["call_options"] = ce_leg
    if pe_leg:
        entry["put_options"] = pe_leg
    return entry


# --------------------------- extraction ---------------------------

def test_extract_candidates_pulls_ce_and_pe_from_each_strike():
    chain = [
        _chain_entry(25000, ce_leg=_leg("NSE|25000CE", 100, 102, 101, 5000, 20000), pe_leg=_leg("NSE|25000PE", 90, 92, 91, 4000, 18000)),
    ]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    assert len(candidates) == 2
    ce = next(c for c in candidates if c.option_type == "CE")
    assert ce.strike == 25000.0
    assert ce.bid == 100
    assert ce.ask == 102
    assert ce.oi == 20000
    assert ce.lot_size > 0


def test_extract_skips_strike_missing_price():
    chain = [{"call_options": _leg("x", 1, 2, 1.5, 1, 1)}]  # no strike_price
    assert extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW) == []


def test_extract_computes_quote_age_seconds():
    fetched_at = NOW - timedelta(seconds=12)
    chain = [_chain_entry(25000, ce_leg=_leg("x", 100, 102, 101, 5000, 20000))]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=fetched_at, now=NOW)
    assert candidates[0].quote_age_seconds == 12.0


# --------------------------- validation ---------------------------

def test_validate_rejects_missing_bid_ask():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", quote_age_seconds=1)
    result = validate_candidate(c)
    assert result.rejected is True
    assert "bid/ask" in result.rejection_reason


def test_validate_rejects_wide_spread():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", bid=100, ask=110, oi=5000, quote_age_seconds=1)
    result = validate_candidate(c, max_spread_pct=0.02)
    assert result.rejected is True
    assert "Spread" in result.rejection_reason


def test_validate_accepts_tight_spread_and_good_liquidity():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", bid=100, ask=101, oi=5000, volume=1000, quote_age_seconds=1)
    result = validate_candidate(c, max_spread_pct=0.02, min_oi=1000)
    assert result.rejected is False


def test_validate_rejects_insufficient_oi():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", bid=100, ask=101, oi=500, quote_age_seconds=1)
    result = validate_candidate(c, min_oi=1000)
    assert result.rejected is True
    assert "OI" in result.rejection_reason


def test_validate_rejects_stale_quote():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", bid=100, ask=101, oi=5000, quote_age_seconds=60)
    result = validate_candidate(c, max_quote_age_seconds=30)
    assert result.rejected is True
    assert "age" in result.rejection_reason


def test_validate_rejects_crossed_quote():
    c = OptionCandidate(instrument_key="x", strike=25000, option_type="CE", expiry="2024-10-31", bid=110, ask=100, oi=5000, quote_age_seconds=1)
    result = validate_candidate(c)
    assert result.rejected is True
    assert "Crossed" in result.rejection_reason


def test_validate_rejects_missing_instrument_key():
    c = OptionCandidate(instrument_key=None, strike=25000, option_type="CE", expiry="2024-10-31", bid=100, ask=101, oi=5000, quote_age_seconds=1)
    result = validate_candidate(c)
    assert result.rejected is True


# --------------------------- selection ---------------------------

def test_select_best_option_prefers_atm():
    chain = [
        _chain_entry(25000, ce_leg=_leg("ATM_CE", 100, 101, 100.5, 5000, 20000)),
        _chain_entry(24950, ce_leg=_leg("ITM_CE", 140, 141, 140.5, 5000, 20000)),
    ]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    best = select_best_option(candidates, option_type="CE", atm_strike=25000.0)
    assert best is not None
    assert best.strike == 25000.0


def test_select_best_option_falls_back_to_itm_when_atm_illiquid():
    chain = [
        _chain_entry(25000, ce_leg=_leg("ATM_CE", 100, 130, 115, 5000, 20000)),  # spread too wide -> rejected
        _chain_entry(24950, ce_leg=_leg("ITM_CE", 140, 141, 140.5, 5000, 20000)),  # good
    ]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    best = select_best_option(candidates, option_type="CE", atm_strike=25000.0, strike_step=50.0)
    assert best is not None
    assert best.strike == 24950.0


def test_select_best_option_itm_direction_for_pe_is_above_atm():
    chain = [
        _chain_entry(25000, pe_leg=_leg("ATM_PE", 100, 130, 115, 5000, 20000)),  # rejected: wide spread
        _chain_entry(25050, pe_leg=_leg("ITM_PE", 140, 141, 140.5, 5000, 20000)),  # ITM for PE is above strike
    ]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    best = select_best_option(candidates, option_type="PE", atm_strike=25000.0, strike_step=50.0)
    assert best is not None
    assert best.strike == 25050.0


def test_select_best_option_returns_none_when_both_atm_and_itm_illiquid():
    chain = [
        _chain_entry(25000, ce_leg=_leg("ATM_CE", 100, 130, 115, 5000, 20000)),
        _chain_entry(24950, ce_leg=_leg("ITM_CE", 100, 130, 115, 5000, 20000)),
    ]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    best = select_best_option(candidates, option_type="CE", atm_strike=25000.0, strike_step=50.0)
    assert best is None


def test_select_best_option_returns_none_when_no_candidates_at_all():
    best = select_best_option([], option_type="CE", atm_strike=25000.0)
    assert best is None


def test_select_best_option_never_considers_beyond_one_strike_itm():
    # Only a 2-strikes-ITM candidate exists — must not be selected.
    chain = [_chain_entry(24900, ce_leg=_leg("FAR_ITM_CE", 180, 181, 180.5, 5000, 20000))]
    candidates = extract_candidates_from_chain(chain, "NIFTY", "2024-10-31", quote_fetched_at=NOW, now=NOW)
    best = select_best_option(candidates, option_type="CE", atm_strike=25000.0, strike_step=50.0)
    assert best is None
