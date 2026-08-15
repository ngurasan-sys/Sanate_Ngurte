"""Pure, stateless logic for manual trading — unit-testable without the
engine, event bus, or network. Mirrors the split already used in
option_analytics (analysis.py vs engine.py).
"""

from typing import Any, Dict, List, Optional


def resolve_strike_row(
    chain: List[Dict[str, Any]], strike: float
) -> Optional[Dict[str, Any]]:
    """Exact strike match if present, else the closest listed strike —
    the chain's actual strike interval (50 for NIFTY, 100 for BANKNIFTY,
    etc.) isn't hardcoded here, so this tolerates a caller-supplied strike
    that doesn't land exactly on the grid.
    """
    if not chain:
        return None
    return min(chain, key=lambda row: abs(row["strike_price"] - strike))


def extract_leg(row: Dict[str, Any], option_type: str) -> Dict[str, Any]:
    """The call_options/put_options sub-dict for the requested side."""
    key = "call_options" if option_type == "CE" else "put_options"
    return row[key]


def compute_weighted_entry_price(
    existing_qty: int, existing_price: float, add_qty: int, add_price: float
) -> float:
    """Quantity-weighted average entry price after adding a pyramid leg."""
    total_qty = existing_qty + add_qty
    if total_qty == 0:
        return 0.0
    return (existing_qty * existing_price + add_qty * add_price) / total_qty


def should_exit(ltp: float, stop_loss: float, target: float) -> Optional[str]:
    """STOP_LOSS_HIT if the premium has fallen to/through the stop, TARGET_HIT
    if it's risen to/through the target, else None. Stop-loss is checked
    first — if both were somehow crossed in one poll interval (a large gap),
    treat it as the loss, not the win.
    """
    if ltp <= stop_loss:
        return "STOP_LOSS_HIT"
    if ltp >= target:
        return "TARGET_HIT"
    return None
