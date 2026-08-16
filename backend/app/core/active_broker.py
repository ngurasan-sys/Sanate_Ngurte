"""Single source of truth for which broker currently drives data feed and
order execution — a SaaS-style "connect one broker, everything uses it"
switch, confirmed with the user as the intended model (exactly one active
broker at a time, never multiple simultaneously). Strategy code,
order_gateway, and every market-data caller resolve "the active broker"
here rather than importing a specific broker's module — so switching the
active broker changes where data comes from and orders go without any
strategy code changing.

Persisted (unlike execution/runtime_state.py's LIVE arm switch, which
deliberately resets on restart as a safety measure) — broker selection is
not a safety switch, so it survives a process restart the same way saved
credentials do.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.app.core.broker_registry import is_known_broker
from backend.app.core.event_bus import event_bus
from backend.app.execution.broker_adapter import BrokerExecutionAdapter
from backend.app.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = _BACKEND_ROOT / ".active_broker.json"


class BrokerSwitchError(Exception):
    """Raised when a broker cannot be made active — unknown broker, not
    ready (no provider/adapter registered, or not connected), or an open
    position would become unmanageable under a different broker."""


@dataclass
class _BrokerRegistration:
    broker_id: str
    provider: Optional[MarketDataProvider] = None
    execution_adapter: Optional[BrokerExecutionAdapter] = None
    auth_module: Optional[object] = None  # exposes load_token() -> Optional[str]


class ActiveBrokerRegistry:
    def __init__(self):
        self._registrations: Dict[str, _BrokerRegistration] = {}
        self._position_checkers: Dict[str, Callable[[], Optional[str]]] = {}
        self._active_broker_id: Optional[str] = self._load_persisted()

    # ---------------------- registration ----------------------

    def register_broker(
        self, broker_id: str, provider: Optional[MarketDataProvider] = None,
        execution_adapter: Optional[BrokerExecutionAdapter] = None,
        auth_module: Optional[object] = None,
    ) -> None:
        existing = self._registrations.get(broker_id)
        if existing is None:
            existing = _BrokerRegistration(broker_id=broker_id)
            self._registrations[broker_id] = existing
        if provider is not None:
            existing.provider = provider
        if execution_adapter is not None:
            existing.execution_adapter = execution_adapter
        if auth_module is not None:
            existing.auth_module = auth_module

    def register_position_checker(self, name: str, checker: Callable[[], Optional[str]]) -> None:
        """checker() returns None if that strategy has no open position
        blocking a broker switch, or a human-readable description of what
        is blocking it."""
        self._position_checkers[name] = checker

    def is_broker_ready(self, broker_id: str) -> bool:
        """True once a provider AND execution adapter are registered for
        broker_id AND its stored credentials produce a real token."""
        reg = self._registrations.get(broker_id)
        if reg is None or reg.provider is None or reg.execution_adapter is None or reg.auth_module is None:
            return False
        return reg.auth_module.load_token() is not None

    # ---------------------- active broker ----------------------

    def get_active_broker_id(self) -> Optional[str]:
        return self._active_broker_id

    def get_active_provider(self) -> Optional[MarketDataProvider]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.provider if reg else None

    def get_active_execution_adapter(self) -> Optional[BrokerExecutionAdapter]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.execution_adapter if reg else None

    def get_active_auth_module(self) -> Optional[object]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.auth_module if reg else None

    def blocking_open_positions(self) -> List[str]:
        blockers = []
        for name, checker in self._position_checkers.items():
            reason = checker()
            if reason:
                blockers.append(f"{name}: {reason}")
        return blockers

    async def set_active_broker(self, broker_id: str) -> None:
        if not is_known_broker(broker_id):
            raise BrokerSwitchError(f"Unknown broker: {broker_id!r}.")
        if not self.is_broker_ready(broker_id):
            raise BrokerSwitchError(
                f"{broker_id} is not connected, or has no data/execution integration registered yet."
            )

        switching_broker = broker_id != self._active_broker_id
        if switching_broker:
            blockers = self.blocking_open_positions()
            if blockers:
                raise BrokerSwitchError(
                    "Cannot switch active broker while positions are open: " + "; ".join(blockers)
                )

        previous_provider = self.get_active_provider()
        if switching_broker and previous_provider is not None:
            await previous_provider.disconnect_feed()

        self._active_broker_id = broker_id
        self._persist()

        new_provider = self.get_active_provider()
        if new_provider is not None:
            await new_provider.connect_feed()

        await event_bus.publish("broker_active_changed", {"broker_id": broker_id})
        logger.info("Active broker set to %s", broker_id)

    # ---------------------- persistence ----------------------

    def _load_persisted(self) -> Optional[str]:
        if not STATE_PATH.exists():
            return None
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data.get("active_broker_id")

    def _persist(self) -> None:
        STATE_PATH.write_text(json.dumps({"active_broker_id": self._active_broker_id}), encoding="utf-8")


active_broker = ActiveBrokerRegistry()
