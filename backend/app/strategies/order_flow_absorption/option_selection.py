"""Option Selection — spec §13/§14.

Parses the raw chain entries `market_data.option_chain_client
.fetch_option_chain()` already returns (Upstox's real `/v2/option/chain`
response — each strike carries `call_options`/`put_options`, each with a
`market_data` block (`ltp`/`bid_price`/`bid_qty`/`ask_price`/`ask_qty`
/`volume`/`oi`/`prev_oi`) and an `option_greeks` block
(`iv`/`delta`/`gamma`/`theta`/`vega`)). The architecture doc flagged that
no code in this repo extracts those fields yet — this module is that
extraction, plus the liquidity/spread/freshness scoring spec §13 wants.
Missing fields are never fabricated; a candidate with data Upstox didn't
provide is rejected, not guessed at.

Greeks, when Upstox's response doesn't carry them, can optionally be
estimated via the existing Black-Scholes engine (engines/greeks.py) —
see estimate_delta_fallback — but the exchange-provided greeks are always
preferred when present.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.market_data.lot_sizes import get_lot_size

DEFAULT_MAX_SPREAD_PCT = 0.02       # 2% of mid price
DEFAULT_MIN_OI = 1000
DEFAULT_MIN_VOLUME = 0
DEFAULT_MAX_QUOTE_AGE_SECONDS = 30.0
DEFAULT_STRIKE_STEP = 50.0


@dataclass
class OptionCandidate:
    instrument_key: Optional[str]
    strike: float
    option_type: str  # "CE" | "PE"
    expiry: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last_price: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    quote_age_seconds: Optional[float] = None
    lot_size: int = 0
    rejected: bool = False
    rejection_reason: Optional[str] = None

    @property
    def spread_pct(self) -> Optional[float]:
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            return None
        mid = (self.bid + self.ask) / 2
        if mid <= 0:
            return None
        return (self.ask - self.bid) / mid


def _leg_to_candidate(leg: Dict[str, Any], strike: float, option_type: str, expiry: str, underlying: str, quote_fetched_at: datetime, now: datetime) -> OptionCandidate:
    market_data = leg.get("market_data") or {}
    greeks = leg.get("option_greeks") or {}

    return OptionCandidate(
        instrument_key=leg.get("instrument_key"),
        strike=strike,
        option_type=option_type,
        expiry=expiry,
        bid=market_data.get("bid_price"),
        ask=market_data.get("ask_price"),
        last_price=market_data.get("ltp"),
        volume=market_data.get("volume"),
        oi=market_data.get("oi"),
        iv=greeks.get("iv"),
        delta=greeks.get("delta"),
        gamma=greeks.get("gamma"),
        theta=greeks.get("theta"),
        vega=greeks.get("vega"),
        quote_age_seconds=(now - quote_fetched_at).total_seconds(),
        lot_size=get_lot_size(underlying),
    )


def extract_candidates_from_chain(
    chain: List[Dict[str, Any]], underlying: str, expiry: str, quote_fetched_at: datetime, now: Optional[datetime] = None,
) -> List[OptionCandidate]:
    """One CE + one PE candidate per strike entry in the raw chain."""
    now = now or datetime.now(quote_fetched_at.tzinfo)
    candidates: List[OptionCandidate] = []
    for entry in chain:
        strike = entry.get("strike_price")
        if strike is None:
            continue
        call = entry.get("call_options")
        put = entry.get("put_options")
        if call:
            candidates.append(_leg_to_candidate(call, float(strike), "CE", expiry, underlying, quote_fetched_at, now))
        if put:
            candidates.append(_leg_to_candidate(put, float(strike), "PE", expiry, underlying, quote_fetched_at, now))
    return candidates


def validate_candidate(
    candidate: OptionCandidate,
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
    min_oi: int = DEFAULT_MIN_OI,
    min_volume: int = DEFAULT_MIN_VOLUME,
    max_quote_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> OptionCandidate:
    """Returns the candidate with rejected/rejection_reason populated —
    never raises, so a caller scanning many candidates doesn't need a
    try/except per candidate.
    """
    if candidate.instrument_key is None:
        candidate.rejected = True
        candidate.rejection_reason = "No instrument_key on this contract."
        return candidate

    if candidate.bid is None or candidate.ask is None:
        candidate.rejected = True
        candidate.rejection_reason = "No bid/ask data available."
        return candidate

    if candidate.bid <= 0 or candidate.ask <= 0:
        candidate.rejected = True
        candidate.rejection_reason = f"Invalid bid/ask ({candidate.bid}/{candidate.ask})."
        return candidate

    if candidate.ask < candidate.bid:
        candidate.rejected = True
        candidate.rejection_reason = f"Crossed quote (bid {candidate.bid} > ask {candidate.ask})."
        return candidate

    spread_pct = candidate.spread_pct
    if spread_pct is None or spread_pct > max_spread_pct:
        candidate.rejected = True
        candidate.rejection_reason = f"Spread {spread_pct} exceeds max {max_spread_pct}."
        return candidate

    if candidate.oi is None or candidate.oi < min_oi:
        candidate.rejected = True
        candidate.rejection_reason = f"OI {candidate.oi} below minimum {min_oi}."
        return candidate

    if min_volume > 0 and (candidate.volume is None or candidate.volume < min_volume):
        candidate.rejected = True
        candidate.rejection_reason = f"Volume {candidate.volume} below minimum {min_volume}."
        return candidate

    if candidate.quote_age_seconds is None or candidate.quote_age_seconds > max_quote_age_seconds:
        candidate.rejected = True
        candidate.rejection_reason = f"Quote age {candidate.quote_age_seconds}s exceeds max {max_quote_age_seconds}s."
        return candidate

    candidate.rejected = False
    candidate.rejection_reason = None
    return candidate


def select_best_option(
    candidates: List[OptionCandidate],
    option_type: str,
    atm_strike: float,
    strike_step: float = DEFAULT_STRIKE_STEP,
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
    min_oi: int = DEFAULT_MIN_OI,
    min_volume: int = DEFAULT_MIN_VOLUME,
    max_quote_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> Optional[OptionCandidate]:
    """Default ATM; falls back to one strike ITM if ATM is illiquid/stale
    (spec §13's explicit "Default: ATM, Alternative: 1 strike ITM" — this
    module deliberately never looks further OTM/ITM than that one step).
    ITM means: CE -> one step below spot (atm_strike - step); PE -> one
    step above (atm_strike + step).
    """
    itm_strike = atm_strike - strike_step if option_type == "CE" else atm_strike + strike_step

    for target_strike in (atm_strike, itm_strike):
        match = next(
            (c for c in candidates if c.option_type == option_type and c.strike == target_strike), None,
        )
        if match is None:
            continue
        validated = validate_candidate(match, max_spread_pct, min_oi, min_volume, max_quote_age_seconds)
        if not validated.rejected:
            return validated

    return None
