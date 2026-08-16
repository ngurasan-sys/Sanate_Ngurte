"""Stop/target/R:R calculation — spec §18/§19.

Stop is always derived from the underlying's absorption-defended level,
never a fixed percentage of option premium (spec §18's explicit
instruction) — the existing risk/execution engine is what translates an
underlying-level stop into actual position protection, not this module.
"""

from dataclasses import dataclass
from typing import Optional

DEFAULT_STOP_BUFFER_PCT = 0.001  # small buffer beyond the defended level
DEFAULT_TARGET_R_MULTIPLE = 1.5


@dataclass
class RiskRewardPlan:
    entry: float
    stop: float
    target: float
    risk_points: float
    reward_points: float
    risk_reward: float
    target_source: str  # "1.5R" | "structural"


def compute_stop(defended_price: float, direction: str, buffer_pct: float = DEFAULT_STOP_BUFFER_PCT) -> float:
    """direction="BULL": stop sits just below the absorption low.
    direction="BEAR": stop sits just above the absorption high.
    """
    buffer = abs(defended_price) * buffer_pct
    return defended_price - buffer if direction == "BULL" else defended_price + buffer


def compute_risk_reward_plan(
    entry: float,
    stop: float,
    direction: str,
    target_r_multiple: float = DEFAULT_TARGET_R_MULTIPLE,
    structural_target: Optional[float] = None,
) -> RiskRewardPlan:
    """structural_target, if given, is only used when it lies *beyond*
    the minimum R-multiple target in the trade's favor — a structural
    level between entry and the R-multiple target would just shrink the
    reward, so it's never allowed to make the plan worse than the
    R-multiple floor.
    """
    if direction == "BULL":
        risk_points = entry - stop
    else:
        risk_points = stop - entry

    if risk_points <= 0:
        raise ValueError(
            f"Non-positive risk ({risk_points}) — stop ({stop}) is on the wrong side of entry ({entry}) for direction {direction}."
        )

    r_multiple_target = entry + risk_points * target_r_multiple if direction == "BULL" else entry - risk_points * target_r_multiple

    target = r_multiple_target
    target_source = f"{target_r_multiple}R"
    if structural_target is not None:
        beyond_r_target = (
            structural_target > r_multiple_target if direction == "BULL" else structural_target < r_multiple_target
        )
        if beyond_r_target:
            target = structural_target
            target_source = "structural"

    reward_points = (target - entry) if direction == "BULL" else (entry - target)
    risk_reward = reward_points / risk_points if risk_points > 0 else 0.0

    return RiskRewardPlan(
        entry=entry, stop=stop, target=target, risk_points=risk_points,
        reward_points=reward_points, risk_reward=risk_reward, target_source=target_source,
    )
