from typing import Optional
from .models import SelectedOption

class StrikeSelectionService:
    @staticmethod
    def select_strike(underlying: str, spot_price: float, direction: str) -> SelectedOption:
        """
        Retrieves the exact instrument key for the target strike using Upstox instrument master data.
        In this implementation, since a full Redis/DuckDB master is assumed to exist downstream,
        we format the instrument key according to Upstox's standard NSE_FO format.
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

        # Upstox Format: NSE_FO|NIFTY23NOV24000CE
        # We will use a placeholder CURRENT_WEEK for the expiry string for now.
        expiry = "CURRENT_WEEK"
        instrument_key = f"NSE_FO|{underlying}{strike}{opt_type}"

        return SelectedOption(
            instrument_key=instrument_key,
            strike_price=strike,
            option_type=opt_type,
            expiry=expiry
        )
