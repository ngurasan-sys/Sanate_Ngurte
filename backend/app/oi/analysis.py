from typing import Optional
from .models import OIState

def calculate_pcr(pe_oi: int, ce_oi: int) -> float:
    """Calculate Put-Call Ratio"""
    if ce_oi == 0:
        return 0.0
    return pe_oi / ce_oi

def classify_buildup(current_price: float, previous_price: float, current_oi: int, previous_oi: int) -> str:
    """Classify basic buildup based on price and OI changes"""
    if current_price > previous_price and current_oi > previous_oi:
        return "LONG_BUILDUP"
    elif current_price < previous_price and current_oi > previous_oi:
        return "SHORT_BUILDUP"
    elif current_price > previous_price and current_oi < previous_oi:
        return "SHORT_COVERING"
    elif current_price < previous_price and current_oi < previous_oi:
        return "LONG_UNWINDING"
    return "NEUTRAL"

def calculate_oi_change_pct(current_oi: int, previous_oi: int) -> float:
    if previous_oi == 0:
        return 0.0
    return ((current_oi - previous_oi) / previous_oi) * 100.0

class OIAnalyzer:
    """Handles analysis on incremental updates"""

    @staticmethod
    def analyze_tick(state: OIState, new_price: float, new_oi: int) -> dict:
        """Returns analysis for the state change"""
        classification = classify_buildup(new_price, state.current_price, new_oi, state.current_oi)
        change_pct = calculate_oi_change_pct(new_oi, state.current_oi)

        return {
            "classification": classification,
            "change_pct": change_pct
        }
