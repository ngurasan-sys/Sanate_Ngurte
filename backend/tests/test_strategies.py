import pytest
from datetime import datetime, timezone
from app.strategies.level_based.support_rejection import SupportRejectionStrategy
from app.market_data.models import Tick
from app.levels.models import Level

@pytest.mark.asyncio
async def test_support_rejection_strategy():
    strategy = SupportRejectionStrategy()

    # Mock a support level
    level = Level(
        level_id="lvl_123", instrument="NIFTY", price=100.0, zone_low=99.5, zone_high=100.5,
        level_type="Support", timeframe="5m", source="test",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
    )

    # Price nearing support
    tick = Tick(instrument="NIFTY", price=100.1, timestamp=datetime.now(timezone.utc))

    # Override emit_signal to capture it
    emitted = []
    async def mock_emit(instrument, direction, level_id, confidence, evidence):
        emitted.append({"dir": direction, "level": level_id})
    strategy.emit_signal = mock_emit

    await strategy.evaluate(tick, [level])

    assert len(emitted) == 1
    assert emitted[0]["dir"] == "BULLISH"
    assert emitted[0]["level"] == "lvl_123"
