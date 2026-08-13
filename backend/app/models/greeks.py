from pydantic import BaseModel
from typing import Optional
from enum import Enum

class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"

class CalcStatus(str, Enum):
    VALID = "VALID"
    INVALID_INPUT = "INVALID_INPUT"
    NO_SOLUTION = "NO_SOLUTION"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

class GreekModel(BaseModel):
    instrument: str
    underlying: str
    expiry: str
    strike: float
    option_type: OptionType
    spot_price: float
    option_price: float
    intrinsic_value: float
    time_to_expiry: float
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    theoretical_price: Optional[float] = None
    timestamp: float
    calculation_status: CalcStatus = CalcStatus.VALID
