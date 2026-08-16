from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator

from .strategies_catalog import STRATEGY_CATALOG


class BacktestRequest(BaseModel):
    underlying: str                    # NIFTY | SENSEX (matches the exported OI data)
    date_from: date
    date_to: date
    strategy: str = "SHORT_STRADDLE"   # key into strategies_catalog.STRATEGY_CATALOG
    lots: int = 1                      # real contract sizing — see engine.py; without this,
                                        # vectorbt defaults to sizing each entry off 100% of
                                        # available cash, which is meaningless for options
    stop_loss_pct: float = 50.0        # % adverse move in the traded premium that triggers a stop
    target_pct: float = 30.0           # % favorable move in the traded premium that triggers a take-profit
    entry_minutes_after_open: int = 5  # skip the first few noisy minutes of the session
    exit_minutes_before_close: int = 5 # square off before the illiquid last minutes

    @field_validator("strategy")
    @classmethod
    def _validate_strategy(cls, v: str) -> str:
        if v not in STRATEGY_CATALOG:
            raise ValueError(f"Unknown strategy {v!r}. Available: {list(STRATEGY_CATALOG)}.")
        return v


class Trade(BaseModel):
    entry_time: datetime
    exit_time: datetime
    strike: float
    entry_price: float   # combined CE+PE premium at entry (short)
    exit_price: float
    pnl: float
    exit_reason: str     # STOP_LOSS | TARGET | TIME_EXIT


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class BacktestResult(BaseModel):
    underlying: str
    date_from: date
    date_to: date
    initial_cash: float
    final_equity: float
    total_return_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct: Optional[float]
    total_trades: int
    trades: List[Trade]
    equity_curve: List[EquityPoint]


class BacktestJob(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"] = "PENDING"
    request: BacktestRequest
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[BacktestResult] = None
    error: Optional[str] = None
