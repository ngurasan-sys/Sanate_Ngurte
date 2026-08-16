"""In-memory runtime arm switch for LIVE trading.

This is the second of the two independent switches required to place a
real order (see order_gateway.resolve_mode). EXECUTION_MODE=LIVE
in the environment is the first switch and is fixed at process start;
this one is toggled at runtime via the frontend's execution-control panel
and always resets to disarmed when the process restarts, so nobody can
leave live trading armed across a deploy or crash by accident.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RuntimeArmState:
    armed: bool = False
    armed_at: Optional[datetime] = None
    note: Optional[str] = None


class ExecutionRuntimeState:
    def __init__(self):
        self._state = RuntimeArmState()

    def arm(self, note: Optional[str] = None) -> RuntimeArmState:
        self._state = RuntimeArmState(armed=True, armed_at=datetime.now(), note=note)
        return self._state

    def disarm(self) -> RuntimeArmState:
        self._state = RuntimeArmState(armed=False, armed_at=None, note=None)
        return self._state

    def is_armed(self) -> bool:
        return self._state.armed

    def snapshot(self) -> RuntimeArmState:
        return self._state


execution_runtime_state = ExecutionRuntimeState()
