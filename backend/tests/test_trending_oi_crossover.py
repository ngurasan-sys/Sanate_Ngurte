import pytest
from datetime import datetime, time
from backend.app.strategies.trending_oi_engine import SpotTrendingOIEngine
from backend.app.market_data.models import Tick, Candle
from backend.app.strategies.trending_oi_price_action.engine import TrendingOIPriceActionStrategy

def test_spot_trending_oi_crossover():
    engine = SpotTrendingOIEngine('NIFTY')
    tick = Tick(instrument='NSE_INDEX|NIFTY', price=24000.0, timestamp=datetime.now())
    engine.process_tick(tick)
    assert 24000.0 in engine.strikes

    engine.process_oi_tick('NIFTY24000CE', 150.0, 20000)
    engine.process_oi_tick('NIFTY24000PE', 140.0, 10000)
    import copy
    engine.completed_rows.append(copy.deepcopy(engine.current_row))

    engine.process_oi_tick('NIFTY24000CE', 160.0, 10000)
    engine.process_oi_tick('NIFTY24000PE', 130.0, 25000)
    assert engine.current_row['crossover'] == 'BULLISH_CROSSOVER'

    engine.completed_rows.append(copy.deepcopy(engine.current_row))

    engine.process_oi_tick('NIFTY24000CE', 160.0, 15000)
    engine.process_oi_tick('NIFTY24000PE', 130.0, 25000)
    assert engine.current_row['crossover'] == 'NO_CROSSOVER'

    engine.completed_rows.append(copy.deepcopy(engine.current_row))

    engine.process_oi_tick('NIFTY24000CE', 160.0, 30000)
    engine.process_oi_tick('NIFTY24000PE', 130.0, 25000)
    assert engine.current_row['crossover'] == 'BEARISH_CROSSOVER'

@pytest.mark.asyncio
async def test_pa_strategy_filters():
    strategy = TrendingOIPriceActionStrategy()
    strategy._get_strike = lambda p, t: '24000CE'
    strategy._emit_signal = lambda *args, **kwargs: None
    state = strategy._get_instrument_state('NIFTY FUT')
    state['last_vwap'] = 24000.0
    state['bullish_oi_confirmed'] = True

    class MockSuperTrend:
        def add_candle(self, h, l, c):
            return {'supertrend': 23990.0, 'trend': 1}
    state['supertrend'] = MockSuperTrend()

    candle = Candle(
        instrument='NIFTY FUT', timeframe='3m', timestamp=datetime.combine(datetime.today(), time(14, 29)),
        open=24010.0, high=24020.0, low=24000.0, close=24010.0, vwap=24000.0, volume=1000
    )
    # Patch execute signal so it doesn't fail
    import asyncio
    async def mock_execute(*args, **kwargs):
        pass
    strategy._execute_signal = mock_execute

    await strategy._handle_candle_closed(candle)
    assert state['time_filter_status'] == 'VALID'
    assert state['distance_filter_status'] == 'VALID'

    candle.timestamp = datetime.combine(datetime.today(), time(14, 31))
    await strategy._handle_candle_closed(candle)
    assert state['time_filter_status'] == 'BLOCKED'
    assert state['trade_valid'] == False

@pytest.mark.asyncio
async def test_pa_strategy_distance_filter():
    strategy = TrendingOIPriceActionStrategy()
    state = strategy._get_instrument_state('NIFTY FUT')
    state['last_vwap'] = 24000.0
    state['bullish_oi_confirmed'] = True

    class MockSuperTrend:
        def add_candle(self, h, l, c):
            # Distance 45 points from 24000
            return {'supertrend': 23955.0, 'trend': 1}
    state['supertrend'] = MockSuperTrend()

    candle = Candle(
        instrument='NIFTY FUT', timeframe='3m', timestamp=datetime.combine(datetime.today(), time(14, 29)),
        open=24010.0, high=24020.0, low=24000.0, close=24010.0, vwap=24000.0, volume=1000
    )

    import asyncio
    async def mock_execute(*args, **kwargs):
        pass
    strategy._execute_signal = mock_execute

    await strategy._handle_candle_closed(candle)
    assert state['distance_filter_status'] == 'BLOCKED'
    assert state['trade_valid'] == False

@pytest.mark.asyncio
async def test_pa_strategy_execution_state():
    strategy = TrendingOIPriceActionStrategy()
    state = strategy._get_instrument_state('NIFTY FUT')
    state['position_state'] = 'TIER_2_ENTERED'
    state['tier_1_status'] = 'FILLED'
    state['tier_2_status'] = 'FILLED'
    state['tier_3_status'] = 'PENDING'
    state['bullish_oi_confirmed'] = True
    state['last_vwap'] = 24000.0
    state['avg_entry_price'] = 24010.0
    state['lots_held'] = 4
    state['current_sl'] = 23990.0
    state['partial_exit_done'] = False

    # We want to trigger the profit reversal
    candle = Candle(
        instrument='NIFTY FUT', timeframe='3m', timestamp=datetime.now(),
        open=24005.0, high=24020.0, low=24000.0, close=24015.0, vwap=24000.0, volume=1000
    )

    # Needs to bypass indicator setup, we can mock supertrend
    class MockSuperTrend:
        def add_candle(self, h, l, c):
            return {'supertrend': 23990.0, 'trend': 1}
    state['supertrend'] = MockSuperTrend()

    # We mock _emit_signal to see if it's called
    emitted = []
    async def mock_emit(action, *args):
        emitted.append(action)
    strategy._emit_signal = mock_emit

    await strategy._handle_candle_closed(candle)

    assert state['tier_3_status'] == 'CANCELLED'
    assert state['partial_exit_done'] == True
    assert state['position_state'] == 'PARTIAL_EXIT'
    assert state['current_sl'] == state['avg_entry_price']
    assert state['lots_held'] < 4 # Partial exit lots deducted
    assert "CANCEL_TIER_3" in emitted
    assert "EXIT_PARTIAL" in emitted
    assert "TRAIL_SL" in emitted
