"""Pure, stateless logic for the IV-regime and PCR-extreme strategies.

Every function here is unit-testable without the engine, the event bus,
or the network.
"""

from typing import Any, Dict, List, Optional, Tuple


def is_valid_iv(iv: Optional[float]) -> bool:
    """Upstox returns iv == 0.0 for illiquid / no-solution strikes (verified
    against the live option chain: deep OTM calls routinely come back with
    "iv": 0.0 while neighbouring liquid strikes report 30-55).

    That is a missing reading, not a real zero-volatility measurement, and
    averaging it in would drag every IV statistic toward zero. Treat it as
    absent.
    """
    return iv is not None and iv > 0.0


def extract_atm_iv(chain: List[Dict[str, Any]], atm_strike: float) -> Optional[float]:
    """Mean of the ATM strike's call and put IV, ignoring invalid readings.
    Returns None when neither side has a usable IV.
    """
    row = next((r for r in chain if r["strike_price"] == atm_strike), None)
    if row is None:
        return None

    call_iv = row.get("call_options", {}).get("option_greeks", {}).get("iv")
    put_iv = row.get("put_options", {}).get("option_greeks", {}).get("iv")

    valid = [iv for iv in (call_iv, put_iv) if is_valid_iv(iv)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def compute_iv_skew(
    chain: List[Dict[str, Any]],
    atm_strike: float,
    strike_offset: int = 3,
) -> Optional[float]:
    """Put IV minus call IV at roughly equidistant OTM strikes.

    Positive => puts are richer than calls (downside fear / put skew).
    Negative => calls richer (upside chase / call skew).
    Returns None when either leg lacks a valid IV.
    """
    sorted_chain = sorted(chain, key=lambda r: r["strike_price"])
    strikes = [r["strike_price"] for r in sorted_chain]
    if atm_strike not in strikes:
        return None

    atm_index = strikes.index(atm_strike)
    put_index = atm_index - strike_offset   # OTM puts sit below spot
    call_index = atm_index + strike_offset  # OTM calls sit above spot

    if put_index < 0 or call_index >= len(sorted_chain):
        return None

    put_iv = sorted_chain[put_index].get("put_options", {}).get("option_greeks", {}).get("iv")
    call_iv = sorted_chain[call_index].get("call_options", {}).get("option_greeks", {}).get("iv")

    if not is_valid_iv(put_iv) or not is_valid_iv(call_iv):
        return None
    return put_iv - call_iv


def classify_skew_bias(skew: Optional[float], threshold: float) -> str:
    if skew is None:
        return "NEUTRAL"
    if skew >= threshold:
        return "PUT_SKEW"
    if skew <= -threshold:
        return "CALL_SKEW"
    return "NEUTRAL"


def classify_iv_regime(
    atm_iv: Optional[float],
    baseline_iv: Optional[float],
    crush_drop_pct: float,
    expansion_rise_pct: float,
) -> Tuple[str, Optional[float]]:
    """Compare the current ATM IV against the intraday baseline.

    Returns (regime, change_pct). Regime is IV_CRUSH when IV has fallen
    meaningfully (premium decaying — favours selling premium),
    IV_EXPANSION when it has risen (favours buying premium), otherwise
    IV_STABLE. UNKNOWN when there isn't enough data to say.
    """
    if atm_iv is None or baseline_iv is None or baseline_iv <= 0:
        return "UNKNOWN", None

    change_pct = ((atm_iv - baseline_iv) / baseline_iv) * 100.0

    if change_pct <= -crush_drop_pct:
        return "IV_CRUSH", change_pct
    if change_pct >= expansion_rise_pct:
        return "IV_EXPANSION", change_pct
    return "IV_STABLE", change_pct


def iv_signal_for_regime(regime: str) -> str:
    """IV crush favours being short premium; expansion favours being long
    premium. Anything else is not a signal.
    """
    if regime == "IV_CRUSH":
        return "SELL_PREMIUM"
    if regime == "IV_EXPANSION":
        return "BUY_PREMIUM"
    return "NONE"


def compute_total_pcr(chain: List[Dict[str, Any]]) -> Optional[float]:
    """Put-Call Ratio across the whole chain, computed from real OI.

    Uses total OI rather than the per-strike `pcr` field so the number
    reflects the entire chain's positioning in one figure.
    """
    total_pe_oi = 0.0
    total_ce_oi = 0.0
    for row in chain:
        total_pe_oi += row.get("put_options", {}).get("market_data", {}).get("oi", 0) or 0
        total_ce_oi += row.get("call_options", {}).get("market_data", {}).get("oi", 0) or 0

    if total_ce_oi <= 0:
        return None
    return total_pe_oi / total_ce_oi


def classify_pcr_zone(pcr: Optional[float], high_extreme: float, low_extreme: float) -> str:
    if pcr is None:
        return "NEUTRAL"
    if pcr >= high_extreme:
        return "HIGH_EXTREME"
    if pcr <= low_extreme:
        return "LOW_EXTREME"
    return "NEUTRAL"


def detect_pcr_reversal(
    pcr: Optional[float],
    pcr_history: List[float],
    high_extreme: float,
    low_extreme: float,
    reversal_delta: float,
) -> Tuple[str, Optional[float], Optional[float], Optional[str]]:
    """A contrarian signal fires only after PCR has *been* at an extreme
    and then turned back from it — not merely by sitting at an extreme,
    which can persist for hours in a trending market.

    Returns (signal, peak, trough, reasoning).
    """
    if pcr is None or not pcr_history:
        return "NONE", None, None, None

    peak = max(pcr_history)
    trough = min(pcr_history)

    if peak >= high_extreme and (peak - pcr) >= reversal_delta:
        return (
            "CONTRARIAN_BULLISH",
            peak,
            trough,
            f"PCR peaked at {peak:.2f} (>= {high_extreme}) and has turned down to "
            f"{pcr:.2f} — excessive put writing unwinding.",
        )

    if trough <= low_extreme and (pcr - trough) >= reversal_delta:
        return (
            "CONTRARIAN_BEARISH",
            peak,
            trough,
            f"PCR bottomed at {trough:.2f} (<= {low_extreme}) and has turned up to "
            f"{pcr:.2f} — excessive call writing unwinding.",
        )

    return "NONE", peak, trough, None


def mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)
