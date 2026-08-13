from typing import Dict
from .models import OIState

class OIPersistence:
    """Handles saving/loading OI state to DuckDB/Parquet (stubbed)"""

    def save_state(self, states: Dict[str, OIState]):
        pass

    def load_state(self) -> Dict[str, OIState]:
        return {}