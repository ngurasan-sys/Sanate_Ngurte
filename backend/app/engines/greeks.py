import math
from scipy.stats import norm
from scipy.optimize import brentq
from typing import Tuple, Optional
from backend.app.models.greeks import OptionType, CalcStatus

class BlackScholes:
    def __init__(self, risk_free_rate: float = 0.0):
        self.r = risk_free_rate

    def d1_d2(self, S: float, K: float, T: float, sigma: float) -> Tuple[float, float]:
        if sigma <= 0 or T <= 0:
            return 0.0, 0.0
        d1 = (math.log(S / K) + (self.r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    def price(self, S: float, K: float, T: float, sigma: float, option_type: OptionType) -> float:
        if T <= 0 or sigma <= 0:
            return max(0.0, S - K) if option_type == OptionType.CALL else max(0.0, K - S)

        d1, d2 = self.d1_d2(S, K, T, sigma)
        if option_type == OptionType.CALL:
            return S * norm.cdf(d1) - K * math.exp(-self.r * T) * norm.cdf(d2)
        else:
            return K * math.exp(-self.r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    def greeks(self, S: float, K: float, T: float, sigma: float, option_type: OptionType) -> dict:
        if T <= 0 or sigma <= 0:
            return {
                "delta": 1.0 if option_type == OptionType.CALL and S > K else (
                         -1.0 if option_type == OptionType.PUT and S < K else 0.0),
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "rho": 0.0
            }

        d1, d2 = self.d1_d2(S, K, T, sigma)

        delta = norm.cdf(d1) if option_type == OptionType.CALL else norm.cdf(d1) - 1
        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T) / 100

        if option_type == OptionType.CALL:
            theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) - self.r * K * math.exp(-self.r * T) * norm.cdf(d2)) / 365
            rho = K * T * math.exp(-self.r * T) * norm.cdf(d2) / 100
        else:
            theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) + self.r * K * math.exp(-self.r * T) * norm.cdf(-d2)) / 365
            rho = -K * T * math.exp(-self.r * T) * norm.cdf(-d2) / 100

        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho
        }

    def implied_volatility(self, S: float, K: float, T: float, market_price: float, option_type: OptionType) -> Tuple[Optional[float], CalcStatus]:
        intrinsic = max(0.0, S - K) if option_type == OptionType.CALL else max(0.0, K - S)
        if market_price < intrinsic:
            return None, CalcStatus.INVALID_INPUT

        if T <= 0:
            return None, CalcStatus.INVALID_INPUT

        def objective_function(sigma):
            return self.price(S, K, T, sigma, option_type) - market_price

        try:
            # Check boundaries first
            if objective_function(1e-6) > 0:
                 return 1e-6, CalcStatus.VALID # price is very low, IV is very low

            if objective_function(5.0) < 0:
                 return None, CalcStatus.NO_SOLUTION # price is too high for IV=500%

            iv = brentq(objective_function, 1e-6, 5.0, xtol=1e-5, maxiter=100)
            return float(iv), CalcStatus.VALID
        except (ValueError, RuntimeError):
            return None, CalcStatus.NUMERICAL_FAILURE

class IVTermStructure:
    @staticmethod
    def calculate_slope(front_expiry_iv: float, next_expiry_iv: float, front_dte: float, next_dte: float) -> dict:
        if next_dte <= front_dte or front_dte <= 0:
            return {"slope": 0.0, "structure": "UNKNOWN"}

        slope = (next_expiry_iv - front_expiry_iv) / (next_dte - front_dte)
        structure = "CONTANGO" if slope > 0 else ("BACKWARDATION" if slope < 0 else "FLAT")
        return {"slope": slope, "structure": structure}

class IVSkew:
    @staticmethod
    def calculate_skew(otm_put_iv: float, atm_iv: float, otm_call_iv: float) -> dict:
        if atm_iv <= 0:
            return {"skew": 0.0, "shape": "UNKNOWN"}

        put_skew = otm_put_iv - atm_iv
        call_skew = otm_call_iv - atm_iv

        skew = otm_put_iv - otm_call_iv
        shape = "SMILE" if (put_skew > 0 and call_skew > 0) else ("SMIRK" if put_skew > call_skew else "FLAT")

        return {"skew": skew, "shape": shape}

class ExpectedMove:
    @staticmethod
    def calculate(spot_price: float, iv: float, dte: float) -> float:
        """
        Calculate expected move based on standard approximation:
        Move = Price * IV * sqrt(Days / 365)
        """
        if dte <= 0 or iv <= 0:
            return 0.0

        return spot_price * iv * (dte / 365.0) ** 0.5
