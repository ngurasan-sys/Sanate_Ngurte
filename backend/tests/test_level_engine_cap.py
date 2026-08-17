from datetime import datetime, timedelta, timezone

import pytest

from backend.app.levels.engine import LevelEngine
from backend.app.levels.models import Level


@pytest.mark.asyncio
async def test_active_levels_capped_and_oldest_dropped():
    engine = LevelEngine()
    inst = "NIFTY"
    base = datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc)

    # Pre-seed well past the cap with distinctly-priced levels, then run one
    # process_candle to trigger the pruning pass.
    engine.active_levels[inst] = [
        Level(
            level_id=f"L{i}",
            instrument=inst,
            price=1000.0 + i * 10,
            zone_low=999.0 + i * 10,
            zone_high=1001.0 + i * 10,
            level_type="Support",
            timeframe="3m",
            source="test",
            created_at=base + timedelta(minutes=i),
            updated_at=base + timedelta(minutes=i),
        )
        for i in range(120)
    ]

    from backend.app.market_data.models import Candle

    await engine.process_candle(
        Candle(
            instrument=inst,
            timeframe="3m",
            timestamp=base,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
    )

    levels = engine.active_levels[inst]
    assert len(levels) == LevelEngine.MAX_ACTIVE_LEVELS
    # oldest dropped: the surviving set is the most recent by created_at
    assert min(l.created_at for l in levels) == base + timedelta(
        minutes=120 - LevelEngine.MAX_ACTIVE_LEVELS
    )


@pytest.mark.asyncio
async def test_only_three_minute_aggregator_feeds_level_engine():
    """The MARKET_TICK -> LevelEngine feed must use exactly one timeframe,
    otherwise LevelEngine's instrument-only-keyed history interleaves
    3m/5m/15m candles and corrupts swing detection."""
    import backend.app.main as main_module
    from backend.app.core.event_bus import event_bus
    from backend.app.market_data.models import Tick

    async with main_module.app.router.lifespan_context(main_module.app):
        closed = []

        async def capture(candle):
            closed.append(candle)

        event_bus.subscribe("CANDLE_CLOSED", capture)

        base = datetime(2024, 1, 1, 9, 15, 0, tzinfo=timezone.utc)
        # 9:15 -> 9:45 crosses 3m, 5m and 15m boundaries; only 3m candles
        # should ever be emitted from this feed.
        for minute in (0, 4, 9, 16, 31):
            await event_bus.publish(
                "MARKET_TICK",
                Tick(
                    instrument="NIFTY",
                    price=100.0 + minute,
                    volume=10,
                    timestamp=base + timedelta(minutes=minute),
                ),
            )

        import asyncio

        await asyncio.sleep(0.05)

        assert closed, "expected at least one closed candle"
        assert {c.timeframe for c in closed} == {"3m"}
