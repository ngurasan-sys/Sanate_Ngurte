"""NSE F&O index-option lot sizes — needed to convert a manual order's
"lots" input into the real contract quantity sent to the broker.

Not available from any Upstox API (checked: option chain / instrument
search return per-strike data, never the contract's lot size). SEBI
revised these market-wide effective 2025-12-31 (part of the phased
increase raising minimum contract value to Rs 15-20 lakh); confirmed via
ICICI Direct's F&O FAQ, cross-checked against a second source, as of
2026-08-16. These do NOT vary by expiry (weekly/monthly/quarterly all use
the same lot size for a given underlying).

SEBI can revise these again — refresh from the official NSE circular
before relying on this for real order sizing if it's been a while since
2026-08-16.
"""

LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "SENSEX": 20,
}


def get_lot_size(underlying: str) -> int:
    """Raises KeyError for an unsupported underlying rather than silently
    guessing — a wrong lot size directly wrongsizes a real order.
    """
    return LOT_SIZES[underlying]
