import time
import pytest
from backend.app.order_flow.engine import OrderFlowEngine
import psutil
import os
import gc
import statistics

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
    # Warmup and caching
    ticks_10k = generate_synthetic_ticks(10000)
    ticks_50k = generate_synthetic_ticks(50000)
    ticks_100k = generate_synthetic_ticks(100000)
    ticks_500k = generate_synthetic_ticks(500000)

    def measure_throughput(ticks, iterations=3):
        durations = []
        for _ in range(iterations):
            engine = OrderFlowEngine()
            start = time.perf_counter()
            for tick in ticks:
                engine.process_tick(tick)
            end = time.perf_counter()
            durations.append(end - start)
        return statistics.median(durations)

    med_10k = measure_throughput(ticks_10k, iterations=5)
    med_50k = measure_throughput(ticks_50k, iterations=5)
    med_100k = measure_throughput(ticks_100k, iterations=3)
    med_500k = measure_throughput(ticks_500k, iterations=1) # 1 iteration is enough given it takes longer and should be stable

    print(f"\nMedian 10k ticks: {med_10k:.4f}s")
    print(f"Median 50k ticks: {med_50k:.4f}s")
    print(f"Median 100k ticks: {med_100k:.4f}s")
    print(f"Median 500k ticks: {med_500k:.4f}s")

    # Asserting approximately linear scaling with tighter boundaries thanks to median
    # Allow 20-30% tolerance to account for GC sweeps or OS interruptions that might occasionally leak through
    assert med_50k < (med_10k * 5) * 1.3
    assert med_100k < (med_50k * 2) * 1.3
    assert med_500k < (med_100k * 5) * 1.3

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

    assert (mem_after - mem_before) / (1024 * 1024) < 50
