from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class DepthLevel(BaseModel):
    price: float
    quantity: int
    orders: int

class DepthData(BaseModel):
    bids: List[DepthLevel] = Field(default_factory=list)
    asks: List[DepthLevel] = Field(default_factory=list)

class Greeks(BaseModel):
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    iv: Optional[float] = None

class FootprintNode(BaseModel):
    price: float
    bid_volume: int = 0
    ask_volume: int = 0
    delta: int = 0
    total_volume: int = 0
    buy_imbalance: bool = False
    sell_imbalance: bool = False
    stacked_zone: Optional[str] = None  # "BUY" | "SELL" | None — set by check_stacked_imbalance

class OrderFlowState(BaseModel):
    instrument_key: str
    timestamp: int
    timeframe: str = "1m"

    classification_mode: str = "UNKNOWN"
    classification_confidence: float = 0.0

    trade_size: int = 0
    trade_size_source: str = "NONE"
    volume_quality: str = "UNKNOWN"

    buy_volume: int = 0
    sell_volume: int = 0
    unknown_volume: int = 0
    bar_delta: int = 0
    cvd: int = 0

    spread: Optional[float] = None
    mid_price: Optional[float] = None

    depth: DepthData = Field(default_factory=DepthData)

    depth_imbalance_1: Optional[float] = None
    depth_imbalance_3: Optional[float] = None
    depth_imbalance_5: Optional[float] = None
    depth_imbalance_10: Optional[float] = None
    depth_imbalance_20: Optional[float] = None
    depth_imbalance_30: Optional[float] = None

    greeks: Optional[Greeks] = None

    footprint: Dict[float, FootprintNode] = Field(default_factory=dict)
