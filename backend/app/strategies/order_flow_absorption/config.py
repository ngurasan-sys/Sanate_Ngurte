"""OFAOConfig — mirrors cas_dislocation/models.py's CASDislocationConfig
pattern exactly: a strategy-scoped config object with its own `enabled`
gate, independent of the shared algo_config_state (which is scoped to a
single underlying's MANUAL-mode capital/pyramid schedule and isn't a fit
for a strategy that trades NIFTY and SENSEX concurrently — see the
architecture doc §21).

`enabled` defaults to False — nothing trades until explicitly turned on,
same safety posture as every other strategy config in this codebase.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class OFAOConfig(BaseModel):
    enabled: bool = False

    underlyings: List[str] = ["NIFTY", "SENSEX"]

    # Absorption Engine (spec §7)
    absorption_strength_threshold: float = 70.0
    absorption_window_candles: int = 3
    min_absorption_candles: int = 2
    absorption_location_tolerance_pct: float = 0.0015  # how close a candle's low/high must be to "near" the location
    absorption_max_break_pct: float = 0.005            # how far price may exceed the location before "failure to follow" collapses to 0

    # Dominance Shift (spec §8)
    imbalance_ratio_pct: float = 400.0  # configurable 200/300/400/500
    dominance_window_candles: int = 3

    # Location Engine (spec §4)
    location_proximity_pct: float = 0.0015
    value_area_pct: float = 0.68

    # Option Selection (spec §13)
    max_spread_pct: float = 0.02
    min_oi: int = 1000
    max_quote_age_seconds: float = 30.0
    strike_step: float = 50.0

    # Risk/Reward (spec §18/§19)
    risk_reward_min: float = 1.5
    target_r_multiple: float = 1.5
    stop_buffer_pct: float = 0.001

    # Market hours (spec — default 09:25 onward, configurable cutoff)
    entry_start_time: str = "09:25"
    entry_cutoff_time: str = "15:00"

    # Sizing — falls back to a fixed lot count; risk_per_trade_pct is
    # informational/reserved for when a capital figure is configured
    # (mirrors algo_config's own "informational only" caveat for
    # percentages that aren't wired to real position sizing yet).
    lots: int = 1
    risk_per_trade_pct: float = 0.5
    trading_capital: Optional[float] = None

    # Signal/data-quality protection (spec §23/§24/§40)
    signal_timeout_seconds: float = 30.0
    max_underlying_drift_pct: float = 0.001  # signal expires if underlying moves this far from trigger before execution

    # Footprint timeframe this strategy evaluates on
    footprint_timeframe: str = "5m"
    structure_base_timeframe: str = "15m"
    structure_1h_bars: int = 4   # 4 x 15m = 1H
    structure_4h_bars: int = 16  # 16 x 15m = 4H

    updated_at: Optional[datetime] = None


class OFAOConfigError(Exception):
    """Raised when a configure request is invalid."""


def validate_config(config: OFAOConfig) -> None:
    if not config.underlyings:
        raise OFAOConfigError("At least one underlying must be configured.")
    for u in config.underlyings:
        if u not in ("NIFTY", "SENSEX", "BANKNIFTY"):
            raise OFAOConfigError(f"Unsupported underlying {u!r}.")
    if config.imbalance_ratio_pct not in (200.0, 300.0, 400.0, 500.0):
        raise OFAOConfigError(
            f"imbalance_ratio_pct must be one of 200/300/400/500, got {config.imbalance_ratio_pct}."
        )
    if config.risk_reward_min < 1.0:
        raise OFAOConfigError("risk_reward_min must be at least 1.0.")
    if config.lots < 1:
        raise OFAOConfigError("lots must be at least 1.")
