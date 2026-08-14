from typing import Dict, Any
from backend.app.engines.greeks import BlackScholes
from backend.app.models.greeks import OptionType, CalcStatus, GreekModel
from backend.app.core.event_bus import event_bus
import time

class GreeksEngine:
    def __init__(self):
        self.bs = BlackScholes(risk_free_rate=0.0)
        self.event_bus = event_bus

    async def calculate_and_publish(self, data: Dict[str, Any]):
        S = data["spot_price"]
        K = data["strike"]
        T = data["time_to_expiry"]
        market_price = data["option_price"]
        option_type = OptionType(data["option_type"])

        iv, status = self.bs.implied_volatility(S, K, T, market_price, option_type)

        greeks = {}
        theoretical_price = None
        if status == CalcStatus.VALID and iv is not None:
            greeks = self.bs.greeks(S, K, T, iv, option_type)
            theoretical_price = self.bs.price(S, K, T, iv, option_type)

        intrinsic_value = max(0.0, S - K) if option_type == OptionType.CALL else max(0.0, K - S)

        greek_model = GreekModel(
            instrument=data["instrument"],
            underlying=data["underlying"],
            expiry=data["expiry"],
            strike=K,
            option_type=option_type,
            spot_price=S,
            option_price=market_price,
            intrinsic_value=intrinsic_value,
            time_to_expiry=T,
            implied_volatility=iv,
            delta=greeks.get("delta"),
            gamma=greeks.get("gamma"),
            theta=greeks.get("theta"),
            vega=greeks.get("vega"),
            rho=greeks.get("rho"),
            theoretical_price=theoretical_price,
            timestamp=data.get("timestamp", time.time()),
            calculation_status=status
        )

        # Publish using existing event bus
        await self.event_bus.publish("GREEKS_UPDATED", greek_model)
