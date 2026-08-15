"""In-memory config/arm state for the CAS Dislocation Engine — same
pattern as engines.algo_config.AlgoConfigState and
execution.runtime_state: resets on process restart, deliberately, so
nobody can leave this armed across a deploy or crash by accident.
"""

from datetime import datetime
from typing import Optional

from .models import CASConfigError, CASDislocationConfig

SUPPORTED_UNDERLYINGS = ("NIFTY", "BANKNIFTY", "SENSEX")


class CASConfigState:
    def __init__(self):
        self._config = CASDislocationConfig()

    def get(self) -> CASDislocationConfig:
        return self._config

    def configure(
        self,
        underlying: str,
        lots: int,
        max_hold_seconds: int = 90,
        min_score_to_alert: int = 60,
        min_score_to_execute: int = 85,
        auto_execute: bool = False,
    ) -> CASDislocationConfig:
        if underlying not in SUPPORTED_UNDERLYINGS:
            raise CASConfigError(f"Unsupported underlying {underlying!r}. Supported: {list(SUPPORTED_UNDERLYINGS)}.")
        if lots <= 0:
            raise CASConfigError("lots must be a positive integer.")
        if max_hold_seconds <= 0:
            raise CASConfigError("max_hold_seconds must be positive.")
        if not (0 <= min_score_to_alert <= 100) or not (0 <= min_score_to_execute <= 100):
            raise CASConfigError("Score thresholds must be between 0 and 100.")
        if min_score_to_execute < min_score_to_alert:
            raise CASConfigError("min_score_to_execute must be >= min_score_to_alert.")

        # Reconfiguring always disarms — same rule as AlgoConfigState:
        # a config change must never silently keep a different, stale
        # setup armed under numbers the trader never confirmed.
        self._config = CASDislocationConfig(
            underlying=underlying,
            enabled=False,
            lots=lots,
            max_hold_seconds=max_hold_seconds,
            min_score_to_alert=min_score_to_alert,
            min_score_to_execute=min_score_to_execute,
            auto_execute=auto_execute,
            updated_at=datetime.now(),
        )
        return self._config

    def enable(self) -> CASDislocationConfig:
        self._config.enabled = True
        return self._config

    def disable(self) -> CASDislocationConfig:
        self._config.enabled = False
        return self._config


cas_config_state = CASConfigState()
