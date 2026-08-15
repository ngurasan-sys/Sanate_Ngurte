"""Pure, stateless scoring logic for the CAS Dislocation Engine —
unit-testable without the engine, event bus, or network, same split as
option_analytics/manual_trading.

The core idea (see the design discussion this module implements): once
continuous cash-market trading ends (~15:15 IST on expiry day), the spot
index freezes, but the futures contract and the options chain keep
trading and keep discovering price. The engine tracks how far the futures
price has moved from the frozen spot, reprices the ATM/near-ATM options
theoretically off that futures-implied level (holding IV at its
pre-freeze baseline, to isolate spot-displacement mispricing from
genuine IV moves), and compares that theoretical value against the
option's actual *executable* bid/ask — not LTP, which can be a stale,
untradable print.

A move where BOTH the CE and PE premiums surge from their pre-freeze
baseline simultaneously is flagged as a volatility/liquidity shock, not a
directional opportunity — a single futures move should push a call up
and a put down (or vice versa), not both up together. That pattern more
likely reflects stale quotes, an IV/liquidity event, or hedge flow than a
tradable directional dislocation, and the engine refuses to signal on it.
"""

import math
from datetime import datetime
from typing import List, Literal, Optional, Tuple

from backend.app.engines.greeks import BlackScholes
from backend.app.models.greeks import OptionType

_bs = BlackScholes(risk_free_rate=0.0)

# Score component weights (sum to 100) — tuned to prioritize the
# dislocation magnitude itself over secondary confirmation signals, since
# a large theoretical-vs-executable gap is the actual trading edge; the
# rest exist to filter out noise/illiquid moves, not to drive the score.
WEIGHT_DISLOCATION = 45
WEIGHT_FUTURE_DISPLACEMENT = 15
WEIGHT_FUTURE_VELOCITY = 15
WEIGHT_SPREAD_QUALITY = 15
WEIGHT_VOLUME_ACCELERATION = 10

# Scaling references — the displacement/velocity/dislocation magnitude at
# which that component alone would max out its weight. Deliberately
# conservative starting points (see AlgoTradingConfig's own precedent):
# tune against real observed expiry-day data before trading on this.
DISPLACEMENT_SCALE_POINTS = 60.0     # futures points from frozen spot
VELOCITY_SCALE_POINTS_PER_SEC = 8.0
DISLOCATION_SCALE_PCT = 0.60         # 60% theoretical-vs-executable gap
VOLUME_ACCEL_SCALE = 5.0             # 5x baseline volume rate


def time_to_expiry_years(expiry_date_str: str, now: datetime, settlement_hour: int = 15, settlement_minute: int = 30) -> float:
    """Minute/second-precision time-to-expiry, needed because this engine
    operates in the last ~15-20 minutes before expiry where day-granularity
    (as used elsewhere, e.g. svi.time_to_expiry_years) is far too coarse —
    T is a few minutes, not a few days, and Black-Scholes is sensitive to
    that at this horizon. Assumes NSE's standard 15:30 IST settlement cutoff.
    """
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    expiry_dt = datetime.combine(expiry_date, datetime.min.time()).replace(
        hour=settlement_hour, minute=settlement_minute, tzinfo=now.tzinfo,
    )
    seconds = (expiry_dt - now).total_seconds()
    return max(seconds, 1.0) / (365.0 * 24.0 * 3600.0)


def theoretical_price(
    future_price: float, strike: float, tau_years: float, iv: float, option_type: Literal["CE", "PE"]
) -> float:
    """Black-76-style approximation: reuses the existing BlackScholes
    class with the futures price standing in for spot and r=0, since the
    futures price already embeds the cost-of-carry the plain B-S formula
    would otherwise need a separate rate for.
    """
    ot = OptionType.CALL if option_type == "CE" else OptionType.PUT
    return _bs.price(S=future_price, K=strike, T=tau_years, sigma=iv, option_type=ot)


def compute_future_displacement(frozen_spot: float, future_price: float) -> float:
    return future_price - frozen_spot


def compute_future_velocity(history: List[Tuple[float, float]], window_seconds: float = 10.0) -> Optional[float]:
    """Points per second over the most recent `window_seconds`.
    `history` is [(epoch_seconds, price), ...] in chronological order.
    None with fewer than 2 samples in the window — no velocity to report.
    """
    if len(history) < 2:
        return None
    latest_t, latest_p = history[-1]
    window = [(t, p) for t, p in history if latest_t - t <= window_seconds]
    if len(window) < 2:
        return None
    earliest_t, earliest_p = window[0]
    dt = latest_t - earliest_t
    if dt <= 0:
        return None
    return (latest_p - earliest_p) / dt


def compute_dislocation_pct(theoretical: float, executable_price: Optional[float]) -> Optional[float]:
    """(theoretical - executable) / theoretical. Positive means the
    option is trading cheap relative to fair value (a buy candidate);
    None when there's no executable price to compare against (e.g. no
    resting ask) or theoretical is non-positive.
    """
    if executable_price is None or theoretical <= 0:
        return None
    return (theoretical - executable_price) / theoretical


def is_volatility_shock(
    ce_current: Optional[float], ce_baseline: Optional[float],
    pe_current: Optional[float], pe_baseline: Optional[float],
    shock_ratio: float = 3.0,
) -> bool:
    """True when BOTH legs have surged by at least `shock_ratio`x from
    their own pre-freeze baseline at the same time — the CE-and-PE-both-
    spike signature described in the design, which a single directional
    futures move cannot produce (that would push one leg up and the other
    down). Needs both baselines to be positive and comparable; returns
    False (not a shock) rather than guessing when data is missing —
    "unknown" must never silently suppress a real signal.
    """
    if not ce_baseline or not pe_baseline or ce_current is None or pe_current is None:
        return False
    return (ce_current / ce_baseline >= shock_ratio) and (pe_current / pe_baseline >= shock_ratio)


def compute_spread_quality(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """0..1, higher = tighter/more executable spread. None when a resting
    quote is missing on either side — can't judge executability without both.
    """
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    spread_frac = (ask - bid) / mid
    return max(0.0, 1.0 - min(spread_frac, 1.0))


def compute_volume_acceleration(recent_volume_delta: float, baseline_volume_rate: float) -> Optional[float]:
    if baseline_volume_rate <= 0:
        return None
    return recent_volume_delta / baseline_volume_rate


def _scaled(value: Optional[float], scale: float, weight: float) -> float:
    if value is None or scale <= 0:
        return 0.0
    return min(abs(value) / scale, 1.0) * weight


def compute_score(
    future_displacement: Optional[float],
    future_velocity: Optional[float],
    ce_dislocation_pct: Optional[float],
    pe_dislocation_pct: Optional[float],
    ce_spread_quality: Optional[float],
    pe_spread_quality: Optional[float],
    volume_acceleration: Optional[float],
) -> int:
    """0-100. See module-level WEIGHT_* / *_SCALE_* constants for the
    breakdown — this just sums the scaled, capped components.
    """
    best_dislocation = max(
        (d for d in (ce_dislocation_pct, pe_dislocation_pct) if d is not None and d > 0),
        default=None,
    )
    spread_quality = max((q for q in (ce_spread_quality, pe_spread_quality) if q is not None), default=None)

    score = (
        _scaled(future_displacement, DISPLACEMENT_SCALE_POINTS, WEIGHT_FUTURE_DISPLACEMENT)
        + _scaled(future_velocity, VELOCITY_SCALE_POINTS_PER_SEC, WEIGHT_FUTURE_VELOCITY)
        + _scaled(best_dislocation, DISLOCATION_SCALE_PCT, WEIGHT_DISLOCATION)
        + (spread_quality * WEIGHT_SPREAD_QUALITY if spread_quality is not None else 0.0)
        + _scaled(volume_acceleration, VOLUME_ACCEL_SCALE, WEIGHT_VOLUME_ACCELERATION)
    )
    return int(round(min(max(score, 0.0), 100.0)))


def classify_signal(
    ce_dislocation_pct: Optional[float], pe_dislocation_pct: Optional[float],
    shock: bool, min_dislocation_pct: float = 0.15,
) -> Literal["NONE", "BUY_CE", "BUY_PE"]:
    """A shock always wins — no directional call while both legs are
    repricing together. Otherwise picks whichever leg is more
    underpriced, provided it clears the minimum dislocation to bother.
    """
    if shock:
        return "NONE"

    ce = ce_dislocation_pct if ce_dislocation_pct is not None else -math.inf
    pe = pe_dislocation_pct if pe_dislocation_pct is not None else -math.inf

    if ce < min_dislocation_pct and pe < min_dislocation_pct:
        return "NONE"
    return "BUY_CE" if ce >= pe else "BUY_PE"
