from typing import Optional

class SpotAnalyzer:
    """Spot specific logic in context of OI (e.g. underlying movement vs derivative OI)"""

    @staticmethod
    def get_spot_context(spot_price: float, prev_spot: float) -> str:
        if spot_price > prev_spot:
            return "UP"
        elif spot_price < prev_spot:
            return "DOWN"
        return "FLAT"