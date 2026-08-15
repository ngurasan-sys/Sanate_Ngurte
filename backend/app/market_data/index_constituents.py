"""Index-weight data for the dispersion-trading basket (Bloch 2016,
SSRN 2715517, Section 7.6) — the `weights` input `implied_correlation_*`,
`realized_correlation`, and `select_dispersion_basket` in
backend/app/strategies/option_analytics/dispersion.py need.

Upstox's option chain / market data APIs do not expose index constituent
weightage anywhere — NSE publishes it in the index factsheet, not via any
broker API. These are point-in-time weights, sourced from NSE index data
via smart-investing.in on 2026-08-16, NOT live-fetched. NSE index
reconstitution and weight rebalancing happen periodically (semi-annually
for full reconstitution; capping/rebalancing can happen more often for
NIFTY BANK specifically) — refresh this list from the official NSE index
factsheet (niftyindices.com) before relying on it for anything beyond
research/backtest, and definitely before live trading.

`symbol` is the plain NSE trading symbol (e.g. "RELIANCE") — the same
form expiry_calendar.fetch_current_week_expiry() already takes as its
`query` argument — not a full Upstox instrument_key. Resolving each
symbol to a live NSE_EQ|<ISIN> instrument_key for a real option-chain
fetch is separate follow-up work, not done here.
"""

from typing import Dict, List

from pydantic import BaseModel


class IndexConstituent(BaseModel):
    symbol: str
    name: str
    weight: float  # fraction of index market cap, e.g. 0.0905 for 9.05%
    sector: str  # NSE's broad sector classification, as listed in the NIFTY 50 factsheet


AS_OF = "2026-08-16"
SOURCE = "https://www.smart-investing.in/indices-bse-nse.php (NSE index constituent weights by market cap)"

NIFTY50_TOP10: List[IndexConstituent] = [
    IndexConstituent(symbol="RELIANCE", name="Reliance Industries Ltd", weight=0.0905, sector="Oil, Gas & Consumable Fuels"),
    IndexConstituent(symbol="BHARTIARTL", name="Bharti Airtel Ltd", weight=0.0635, sector="Telecommunication"),
    IndexConstituent(symbol="HDFCBANK", name="HDFC Bank Ltd", weight=0.0573, sector="Financial Services"),
    IndexConstituent(symbol="ICICIBANK", name="ICICI Bank Ltd", weight=0.0520, sector="Financial Services"),
    IndexConstituent(symbol="SBIN", name="State Bank of India", weight=0.0504, sector="Financial Services"),
    IndexConstituent(symbol="TCS", name="Tata Consultancy Services Ltd", weight=0.0436, sector="Information Technology"),
    IndexConstituent(symbol="BAJFINANCE", name="Bajaj Finance Ltd", weight=0.0346, sector="Financial Services"),
    IndexConstituent(symbol="LT", name="Larsen & Toubro Ltd", weight=0.0286, sector="Construction"),
    IndexConstituent(symbol="HINDUNILVR", name="Hindustan Unilever Ltd", weight=0.0251, sector="Fast Moving Consumer Goods"),
    IndexConstituent(symbol="INFY", name="Infosys Ltd", weight=0.0242, sector="Information Technology"),
]

BANKNIFTY_TOP7: List[IndexConstituent] = [
    IndexConstituent(symbol="HDFCBANK", name="HDFC Bank Ltd", weight=0.2329, sector="Financial Services"),
    IndexConstituent(symbol="ICICIBANK", name="ICICI Bank Ltd", weight=0.2114, sector="Financial Services"),
    IndexConstituent(symbol="SBIN", name="State Bank of India", weight=0.2048, sector="Financial Services"),
    IndexConstituent(symbol="KOTAKBANK", name="Kotak Mahindra Bank Ltd", weight=0.0812, sector="Financial Services"),
    IndexConstituent(symbol="AXISBANK", name="Axis Bank Ltd", weight=0.0787, sector="Financial Services"),
    IndexConstituent(symbol="UNIONBANK", name="Union Bank of India", weight=0.0297, sector="Financial Services"),
    IndexConstituent(symbol="PNB", name="Punjab National Bank", weight=0.0281, sector="Financial Services"),
]

INDEX_BASKETS: Dict[str, List[IndexConstituent]] = {
    "NIFTY": NIFTY50_TOP10,
    "BANKNIFTY": BANKNIFTY_TOP7,
}


def get_constituents(index_key: str) -> List[IndexConstituent]:
    """Raises KeyError for an unknown index rather than silently returning
    an empty basket — a dispersion trade sized off zero constituents would
    be a silent no-op, not an obvious error.
    """
    return INDEX_BASKETS[index_key]


def total_weight_covered(index_key: str) -> float:
    """Sum of the captured constituents' weights — how much of the real
    index this partial basket actually represents. NIFTY top 10 covers
    less than half the index by design (50 constituents, long tail);
    BANKNIFTY top 7 covers most of it (only ~12-14 constituents total,
    heavily concentrated in the top 3).
    """
    return sum(c.weight for c in get_constituents(index_key))
