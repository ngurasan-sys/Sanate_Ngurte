from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ManualOrderRequest(BaseModel):
    underlying: str            # NIFTY | BANKNIFTY | SENSEX (see lot_sizes.LOT_SIZES)
    option_type: Literal["CE", "PE"]
    strike: Optional[float] = None   # None => ATM, resolved from the live chain
    expiry_date: str = "current_week"  # matches option_chain_client's expiry_date param
    lots: int
    stop_loss: float           # premium price — position auto-closes at/below this
    target: float              # premium price — position auto-closes at/above this
    pyramid_lot_size: int = 0  # lots added per "Add Pyramid Lot" click; 0 = pyramiding disabled


class ManualPosition(BaseModel):
    position_id: str
    underlying: str
    option_type: Literal["CE", "PE"]
    strike: float
    instrument_token: str
    expiry_date: str
    lots: int
    quantity: int               # lots * lot_size, the real contract quantity
    entry_price: float          # quantity-weighted average across entry + pyramids
    stop_loss: float
    target: float
    pyramid_lot_size: int
    # PENDING: DECISION_CREATED submitted, RISK_DECISION/EXECUTION_UPDATE
    # not back yet — never reported as OPEN until risk+execution actually
    # confirm it. A risk-rejected or execution-rejected entry moves
    # straight to CLOSED with exit_reason set; it never becomes OPEN.
    status: Literal["PENDING", "OPEN", "CLOSED"] = "PENDING"
    created_at: datetime
    closed_at: Optional[datetime] = None
    exit_reason: Optional[str] = None  # MANUAL_CLOSE | STOP_LOSS_HIT | TARGET_HIT
    last_ltp: Optional[float] = None
