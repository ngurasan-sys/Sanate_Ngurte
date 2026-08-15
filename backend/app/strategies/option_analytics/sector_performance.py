"""Sector-level aggregation of the NIFTY/BANKNIFTY dispersion basket
(backend/app/market_data/index_constituents.py) — the "factor dispersion"
idea: reduce a multi-name basket to a handful of sector returns, cheaper
to trade and reason about than 10-50 individual names (see the notes on
factor dispersion vs full single-stock dispersion under Bloch (2016)
Section 7.6, SSRN 2715517 — the paper itself only covers single-stock
dispersion; sector aggregation is standard market practice layered on top
of it, not something the paper specifies).

Every constituent in both baskets carries NSE's broad sector
classification (as listed alongside each name in the NIFTY 50 factsheet).
NIFTY50_TOP10 spans six sectors; BANKNIFTY_TOP7 is entirely "Financial
Services" by construction (it's a sector index), so sector aggregation is
a no-op there — this module is meaningful for the NIFTY basket, not
BANKNIFTY.

No live price feed is wired here — `returns` is a plain
{symbol: pct_return} mapping the caller supplies (from LTP vs close, an
order-flow tick, or a backtest's return series). Kept pure and
network-free, same as dispersion.py and variance.py in this package.
"""

from collections import defaultdict
from typing import Dict, List, Tuple

from backend.app.market_data.index_constituents import IndexConstituent


def compute_sector_returns(
    returns: Dict[str, float], universe: List[IndexConstituent]
) -> Dict[str, float]:
    """Index-weighted average return per sector, using each constituent's
    weight *within its sector* (i.e. renormalized against only the other
    constituents sharing that sector) — so a sector's reading isn't
    diluted just because a big name from a different sector is also
    present in `universe`.

    Constituents missing from `returns` are skipped (their tick hasn't
    arrived, or that symbol's price wasn't supplied) rather than treated
    as a zero return, which would silently bias the sector average.
    """
    sector_weight: Dict[str, float] = defaultdict(float)
    sector_weighted_return: Dict[str, float] = defaultdict(float)

    for c in universe:
        if c.symbol not in returns:
            continue
        sector_weight[c.sector] += c.weight
        sector_weighted_return[c.sector] += c.weight * returns[c.symbol]

    return {
        sector: sector_weighted_return[sector] / sector_weight[sector]
        for sector in sector_weight
        if sector_weight[sector] > 0
    }


def rank_sectors(sector_returns: Dict[str, float]) -> List[Tuple[str, float]]:
    """Best-performing sector first — cheap way to see which sector is
    actually driving the index move versus which are flat or dragging.
    """
    return sorted(sector_returns.items(), key=lambda kv: kv[1], reverse=True)
