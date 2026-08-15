from typing import Optional
from .models import SelectedOption

class StrikeSelectionService:
    @staticmethod
    def select_strike(underlying: str, spot_price: float, direction: str) -> SelectedOption:
        """
        Computes the ATM strike and option type for the target setup.

        NOTE: no Upstox instrument-master lookup is wired up yet, so the
        real expiry date cannot be resolved here. `expiry` is returned as
        the literal string "UNRESOLVED" and `instrument_key` deliberately
        omits an expiry segment — it is NOT a valid, order-placeable Upstox
        instrument key. Do not use this key for real order placement until
        expiry resolution against the real instrument master is implemented.
        """
        step = 50
        if underlying == "BANKNIFTY":
            step = 100
        elif underlying == "SENSEX":
            step = 100

        atm_strike = round(spot_price / step) * step

        if direction == "BULLISH":
            strike = atm_strike
            opt_type = "CE"
        else:
            strike = atm_strike
            opt_type = "PE"

        expiry = "UNRESOLVED"
        instrument_key = f"NSE_FO|{underlying}{strike}{opt_type}|EXPIRY_UNRESOLVED"

        return SelectedOption(
            instrument_key=instrument_key,
            strike_price=strike,
            option_type=opt_type,
            expiry=expiry
        )
