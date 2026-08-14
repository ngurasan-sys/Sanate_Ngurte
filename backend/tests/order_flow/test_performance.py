import time
import statistics
import os
import gc
import sys
import pytest

from backend.app.order_flow.engine import OrderFlowEngine

try:
    import psutil
except Exception:
    psutil = None


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


def _run_and_measure(engine, ticks):
    gc.collect()
    if psutil:
        proc = psutil.Process(os.getpid())
        mem_before = proc.memory_info().rss
    else:
        mem_before = None

    t0 = time.perf_counter()
    for tick in ticks:
        engine.process_tick(tick)
    t1 = time.perf_counter()

    if psutil:
        mem_after = proc.memory_info().rss
    else:
        mem_after = None

    duration = t1 - t0
    return duration, mem_before, mem_after


@pytest.mark.timeout(900)
def test_engine_performance_linear_scaling_median_runs():
    """Run multiple measurements and assert approximate linear scaling using medians.

    This keeps the 500k coverage but makes the measurement robust to CI jitter by
    using repeated runs and medians instead of single-run assertions.
    """
    runs = 3
    instruments = 1

    sizes = [10_000, 50_000, 100_000, 500_000]

    # store median durations per size
    medians = {}
    mem_deltas = {}

    for n in sizes:
        durations = []
        mems = []
        ticks = generate_synthetic_ticks(n)
        for _ in range(runs):
            engine = OrderFlowEngine()
            duration, mem_before, mem_after = _run_and_measure(engine, ticks)
            durations.append(duration)
            if mem_before is not None and mem_after is not None:
                mems.append(mem_after - mem_before)
            # small pause to reduce cross-run interference
            time.sleep(0.1)
        del ticks
        gc.collect()
        med = statistics.median(durations)
        medians[n] = med
        mem_deltas[n] = statistics.median(mems) if mems else None

    # Assert approximately linear scaling (O(N)): time should not grow superlinearly
    assert medians[50_000] < (medians[10_000] * 5) * 2.5, f"Scaling 10k->50k not linear enough: {medians[50_000]} vs {medians[10_000]*5}"
    assert medians[100_000] < (medians[50_000] * 2) * 2.5, f"Scaling 50k->100k not linear enough: {medians[100_000]} vs {medians[50_000]*2}"
    assert medians[500_000] < (medians[100_000] * 5) * 2.5, f"Scaling 100k->500k not linear enough: {medians[500_000]} vs {medians[100_000]*5}"

    # Throughput sanity: ensure we processed 500k ticks in reasonable time
    t_500k = medians[500_000]
    tps_500k = 500_000 / t_500k
    # baseline throughput expectation; adjust as needed for your CI machines
    min_tps = 500
    assert tps_500k >= min_tps, f"Throughput too low for 500k run: {tps_500k:.1f} ticks/s"

    # Bounded memory: ensure footprint doesn't grow unbounded for the final engine
    final_engine = OrderFlowEngine()
    ticks = generate_synthetic_ticks(500_000)
    for tick in ticks:
        final_engine.process_tick(tick)
    state = final_engine.get_state("NIFTY")
    assert state is not None
    # synthetic data uses 10 price levels, footprint should be <= 10
    assert len(state.footprint) <= 10

    # Optional memory delta check if psutil available
    if psutil:
        delta = mem_deltas[500_000]
        if delta is not None:
            # Allow up to 200MB growth in CI; this is a conservative upper bound
            assert delta < 200 * 1024 * 1024, f"Memory grew too much: {delta} bytes"
