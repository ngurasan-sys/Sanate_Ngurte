from typing import Optional
from .models import OIState

class FuturesAnalyzer:
    """Futures specific OI logic (basis, premium, etc.)"""
    @staticmethod
    def calculate_basis(futures_price: float, spot_price: float) -> float:
        if spot_price == 0:
            return 0.0
        return futures_price - spot_price

    @staticmethod
    def get_futures_state_summary(state: OIState) -> dict:
        return {
            "price": state.current_price,
            "oi": state.current_oi,
            "is_premium": True # stub
        }