import pytest


@pytest.mark.asyncio
async def test_level_engine_registered_and_subscribed_to_market_tick():
    import backend.app.main as main_module
    from backend.app.api.endpoints.levels import get_level_engine
    from backend.app.core.event_bus import event_bus
    from backend.app.market_data.models import Tick
    from datetime import datetime, timezone

    # main.py registers set_level_engine(...) at import time is NOT the
    # pattern used elsewhere in this codebase (active_broker registration
    # is import-time, but engine construction/wiring happens inside
    # lifespan) — so this test drives the lifespan startup directly.
    async with main_module.app.router.lifespan_context(main_module.app):
        engine = get_level_engine()
        assert engine is not None

        published = []

        async def capture(data):
            published.append(data)

        event_bus.subscribe("CANDLE_CLOSED", capture)

        # Feed enough ticks across 3m candle boundaries to force at least
        # one candle close on the fastest (3-minute) aggregator.
        base = datetime(2024, 1, 1, 9, 15, 0, tzinfo=timezone.utc)
        await event_bus.publish("MARKET_TICK", Tick(instrument="NIFTY", price=100.0, volume=10, timestamp=base))
        await event_bus.publish("MARKET_TICK", Tick(instrument="NIFTY", price=105.0, volume=10, timestamp=base.replace(minute=18)))

        import asyncio
        await asyncio.sleep(0.05)

        assert len(published) >= 1
