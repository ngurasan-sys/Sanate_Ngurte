import time
import pytest
from backend.app.order_flow.engine import OrderFlowEngine
import psutil
import os
import gc

def generate_synthetic_ticks(count, instrument_key="NIFTY"):
    ticks = []
    for i in range(count):
        # Alternate bid/ask
        best_bid = 100.0 + (i % 10) * 0.1
        best_ask = best_bid + 0.1

        ltp = best_ask if i % 2 == 0 else best_bid

        ticks.append({
            "instrument_key": instrument_key,
            "ltt": 1000 + i,
            "ltp": ltp,
            "ltq": 10,
            "volume": (i + 1) * 10,
            "market_depth": {
                "bids": [{"price": best_bid, "quantity": 100, "orders": 1}],
                "asks": [{"price": best_ask, "quantity": 100, "orders": 1}]
            }
        })
    return ticks

def test_engine_performance_linear_scaling():
    engine = OrderFlowEngine()

    # Warmup
    ticks_10k = generate_synthetic_ticks(10000)

    start_time = time.time()
    for tick in ticks_10k:
        engine.process_tick(tick)
    duration_10k = time.time() - start_time

    # 50k
    ticks_50k = generate_synthetic_ticks(50000)
    engine = OrderFlowEngine() # Reset
    start_time = time.time()
    for tick in ticks_50k:
        engine.process_tick(tick)
    duration_50k = time.time() - start_time

    # 100k
    ticks_100k = generate_synthetic_ticks(100000)
    engine = OrderFlowEngine() # Reset
    start_time = time.time()
    for tick in ticks_100k:
        engine.process_tick(tick)
    duration_100k = time.time() - start_time

    # 500k
    ticks_500k = generate_synthetic_ticks(500000)
    engine = OrderFlowEngine() # Reset
    start_time = time.time()
    for tick in ticks_500k:
        engine.process_tick(tick)
    duration_500k = time.time() - start_time

    print(f"\n10k ticks: {duration_10k:.4f}s")
    print(f"50k ticks: {duration_50k:.4f}s")
    print(f"100k ticks: {duration_100k:.4f}s")
    print(f"500k ticks: {duration_500k:.4f}s")

    # Verify linear scaling (allow 50% margin for variability in small numbers)
    # duration_50k should be ~5x duration_10k
    # duration_100k should be ~2x duration_50k
    # duration_500k should be ~5x duration_100k

    assert duration_50k < (duration_10k * 5) * 2.0
    assert duration_100k < (duration_50k * 2) * 1.5
    assert duration_500k < (duration_100k * 5) * 1.5

    # Verify bounded memory - footprint should not grow unbounded
    state = engine.get_state("NIFTY")
    # Footprint size is bounded by the number of unique prices in the synthetic generator (10 prices)
    assert len(state.footprint) <= 10

def test_bounded_state():
    gc.collect()
    engine = OrderFlowEngine()

    process = psutil.Process(os.getpid())

    ticks = generate_synthetic_ticks(500000)

    gc.collect()
    mem_before = process.memory_info().rss

    for tick in ticks:
        engine.process_tick(tick)

    gc.collect()
    mem_after = process.memory_info().rss

    # Engine state should not consume more than a few MBs extra.
    # Allowing up to 50MB for general Python interpreter overhead during execution.
    assert (mem_after - mem_before) / (1024 * 1024) < 50
