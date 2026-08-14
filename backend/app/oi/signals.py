from typing import List, Callable
from .models import OIStrategyOutput

class OISignalDispatcher:
    """Dispatches generated OI strategy signals to the Opportunity Engine"""

    def __init__(self):
        self.handlers: List[Callable[[OIStrategyOutput], None]] = []

    def register_handler(self, handler: Callable[[OIStrategyOutput], None]):
        self.handlers.append(handler)

    def dispatch(self, signal: OIStrategyOutput):
        for handler in self.handlers:
            handler(signal)