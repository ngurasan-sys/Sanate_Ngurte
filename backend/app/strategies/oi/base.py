from abc import ABC, abstractmethod
from typing import Optional
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class BaseOIStrategy(ABC):
    """Base class for all OI Strategies"""

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    @abstractmethod
    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        """
        Analyzes the current state and tick, returning a signal if conditions are met.
        """
        pass