# ORDER_FLOW_ABSORPTION_OPTIONS (OFAO) — Architecture & Integration Plan

Status: **inspection complete, no strategy code written yet** — per the explicit instruction to wait for approval before implementing.

This document maps every piece of existing Sanate infrastructure OFAO must reuse, the exact integration point into the existing risk/execution pipeline, and what's genuinely missing and must be built new.

---

## 1. Existing architecture (the trade pipeline)

Two proven paths reach the broker today. Understanding both — and why the first one is unsuitable for OFAO — is the single most important finding in this document.

### Path A: the "generic" pipeline (STRATEGY_SIGNAL → Opportunity → Decision → Risk → Execution)

```
strategy engine
  → event_bus.publish("STRATEGY_SIGNAL", {...})
  → OpportunityEngine.process_signal()      (backend/app/engines/opportunity.py)
  → event_bus.publish("OPPORTUNITY_CREATED")
  → DecisionEngine.process_opportunity()    (backend/app/engines/decision.py)
  → event_bus.publish("DECISION_CREATED")
  → RiskEngine.process_decision()           (backend/app/engines/risk.py)
  → event_bus.publish("EXECUTION_REQUEST")
  → ExecutionEngine.execute_order()         (backend/app/engines/execution.py)
  → order_gateway.place_order()             (backend/app/execution/order_gateway.py)
```

Used today by: ATR Strategies, Gap Opening, Trending OI+Price Action, Intraday Trend Scalper, Expiry Reversal (all fixed for STRATEGY_SIGNAL wiring earlier this session).

**Why OFAO cannot use this path**: `DecisionEngine.process_opportunity()` builds its `Decision` object from only `opportunity_id`, `instrument`, and `confidence` — the `Decision` Pydantic model has **no `quantity`, `instrument_token`, or `price` field at all**. Even if OFAO's signal carried a fully-resolved option contract and sized quantity, `model_dump()` would drop them before RiskEngine ever sees them, and RiskEngine would evaluate a `quantity=0` order. This path is real but structurally incapable of placing a properly-sized, instrument-specific order today. It is not an OFAO-specific problem — every strategy on this path shares it.

### Path B: the "direct decision" pattern (used by CAS Dislocation and Manual Trading)

```
strategy engine (fully resolves instrument_token, quantity, price itself)
  → event_bus.publish("DECISION_CREATED", {... source: "CAS_DISLOCATION" ...})
  → RiskEngine.process_decision()   [same RiskEngine, same evaluate_all()]
  → event_bus.publish("EXECUTION_REQUEST")
  → ExecutionEngine → order_gateway.place_order()
```

`backend/app/strategies/cas_dislocation/engine.py` (`_open_position`/`_close_position`, lines ~309-355) is the reference implementation: it resolves a real instrument, computes `quantity = config.lots * lot_size`, and publishes a complete `DECISION_CREATED` payload directly — skipping the broken Path A entirely. `RiskEngine.process_decision()` branches on `source`:

```python
if source == "ALGO":
    # evaluate_algo_extra: algo_config_state's single-underlying capital
    # budget + pyramid schedule (MANUAL mode only)
elif source == "CAS_DISLOCATION":
    # check_cas_enabled: CAS's own independent enabled flag
```

**This is the integration point OFAO should use** — see §10.

---

## 2. Existing Order Flow Footprint

`backend/app/order_flow/` (recently extended this session):

- `engine.py` (`OrderFlowEngine`) — per-instrument, continuously-accumulating tick classification (`AGGRESSIVE_BUY`/`AGGRESSIVE_SELL`/`UNKNOWN` via best-bid/ask + tick rule), running `buy_volume`/`sell_volume`/`bar_delta`/`cvd`, multi-level depth imbalance (`depth_imbalance_1/3/5/10/20/30`).
- `footprint_candle.py` (`FootprintCandleAggregator`) — **the piece that gives OFAO discrete OHLC candles with a footprint dict per timeframe** (1m/3m/5m/15m), each level flagged with `buy_imbalance`/`sell_imbalance`/`stacked_zone` via `analysis.check_diagonal_imbalance`/`check_stacked_imbalance` (both real, tested functions — `check_stacked_imbalance` was dead code until this session's fix).
- `analysis.py` — pure functions: `classify_trade_direction`, `calculate_trade_size`, `calculate_depth_imbalance`, `check_diagonal_imbalance(footprint, ratio)`, `check_stacked_imbalance(footprint, min_consecutive)`.
- `models.py` — `FootprintNode` (price, bid_volume, ask_volume, delta, total_volume, buy_imbalance, sell_imbalance, stacked_zone), `OrderFlowState`.

**OFAO's Absorption Engine (§6 of the spec) reuses `FootprintCandle`/`FootprintNode` and the diagonal/stacked-imbalance functions directly.** No new footprint math needed — OFAO needs a layer *on top* that interprets a sequence of footprint candles as "aggression followed by failure to extend" (absorption), which does not exist yet (see §5 below).

**Critical caveat carried over from the footprint build**: the only tick source currently feeding this engine for NIFTY/SENSEX/BANKNIFTY *futures* is `mock_feed.py` — a deliberately simulated random-walk generator, isolated on its own `footprint_mock_tick` channel. **There is no real Level-2 futures depth feed wired into this app.** The live Upstox connection (`upstox_v3.py`) runs in `ltpc` mode against *index spot* instruments only — no market depth, no volume field at all. OFAO's absorption/imbalance detection would run against simulated data until a real `full`/`full_d30` Upstox futures subscription is built (a separate integration task, out of scope here). **This is the single most important gap for "the strategy must be capable of generating REAL LIVE TRADES."**

---

## 3. Existing live market data

| Feed | File | What it actually provides |
|---|---|---|
| Index spot ticks | `market_data/upstox_v3.py` | `ltpc` mode: LTP only. No volume, no depth. Publishes `MARKET_TICK`. |
| Candle aggregation | `market_data/processor.py` (`TickProcessor`) | 3m/5m/15m OHLC candles from `MARKET_TICK`, **including session VWAP** — but VWAP only accumulates when `tick.volume` is truthy, which the live `ltpc` feed never provides (hardcoded `volume=0.0`, see upstox_v3.py's own comment). **VWAP is non-functional on the real live feed today.** It works fine against historical/mock data that does carry volume. |
| Historical candles | `market_data/historical_candles.py` | Used for backtesting, not live. |
| Option chain | `market_data/option_chain_client.py` | Real Upstox `/v2/option/chain` REST call. Returns `oi`/`prev_oi`/`ltp`/`close_price` + `underlying_spot_price` per strike, per the module's own docstring. **Bid/ask, volume, and Greeks are not currently extracted anywhere in this codebase** — needs verification against Upstox's raw response shape before OFAO's liquidity/spread checks (spec §13/§24) can rely on it. |
| Futures instrument resolution | `market_data/futures_instrument.py` | Resolves the real current-month futures `instrument_key` via Upstox Instrument Search — requires a live OAuth token. |
| Expiry resolution | `market_data/expiry_calendar.py` | Resolves whether today is expiry day via Upstox Instrument Search (used by Expiry Reversal). Not the same as option-contract expiry selection. |
| Session phase | `api/session_phase.py` | Pure function: `CLOSED`/`CONTINUOUS`/`DECAY`/`CAS`/`GOLDEN_WINDOW` by time-of-day. No trading-day/holiday calendar exists anywhere. |
| Lot sizes | `market_data/lot_sizes.py` | `get_lot_size(underlying)` — NIFTY/BANKNIFTY/SENSEX all defined. |

## 4/5. NIFTY and SENSEX futures/spot feeds

Same `upstox_v3.py` mechanism, `ltpc` mode. No dedicated futures depth subscription exists — every live strategy that references `"NIFTY FUT"`/`"SENSEX FUT"` as an instrument key (Intraday Trend Scalper, Trending OI+PA, ATR, Expiry Reversal, Pullback Chop Filter) is naming a *conceptual* instrument, not a real, separately-subscribed futures feed with its own depth.

## 6. Option quote feed

No dedicated live option *quote* (tick-by-tick LTP/bid/ask) stream exists — only the periodic REST option-chain pull described above. "Quote freshness" (spec §13, §17, §24) will need to be defined as "age since the last successful `/v2/option/chain` fetch," not tick-level freshness, unless a new subscription is built.

## 7. Existing VWAP

Covered in §3 — `Candle.vwap`, cumulative-session, computed in `TickProcessor.process_tick`. Real but silently inert on the live feed (no volume). OFAO's VWAP contextual check (spec §3) needs this fixed (get real volume into the futures feed) or an explicit fallback/warning state, not a silent `None`.

## 8/9. Volume profile, POC, VAH, VAL, HVN, LVN

**None of this exists anywhere in the codebase.** Confirmed via repository-wide search — no `POC`, `VAH`, `VAL`, or volume-profile module in `backend/app/`. This is core to spec §2 (Value Structure) and therefore to the Location Engine (§4) — **it is new work, not reuse**, though it can be built on top of the existing `Candle`/tick-volume data once real volume exists.

## 10. Existing delta

`OrderFlowState.bar_delta`/`.cvd` (continuous, per-instrument) and `FootprintCandle.delta`/`FootprintNode.delta` (per-candle, per-price-level) — both real and reusable directly for the Absorption Engine's delta-percentile checks (spec §7).

## 11. Existing imbalance

`depth_imbalance_1/3/5/10/20/30` (order book depth ratio, engine.py) and `check_diagonal_imbalance`/`check_stacked_imbalance` (footprint-based, analysis.py) — both real, reusable, and configurable by ratio exactly as spec §8 wants (200%-500% dial already built for the footprint UI, same math OFAO's Dominance Shift stage needs).

## 12. Existing trade engine

Covered in §1 — Path A (broken for sized orders) and Path B (proven, OFAO's target).

## 13. Existing LIVE/PAPER switch

`backend/app/execution/order_gateway.py` — **this already satisfies spec §35 almost exactly**, with terminology worth calling out: modes are `DRY_RUN` / `SANDBOX` / `LIVE`, not literally "PAPER"/"LIVE". `DRY_RUN` (default) logs the exact payload with zero network calls — functionally "paper mode" in the strategy's eyes. `LIVE` requires **two independent confirmations** (`UPSTOX_EXECUTION_MODE=LIVE` env var *and* either `UPSTOX_LIVE_TRADING_CONFIRMED=YES` or the frontend's runtime arm switch, `execution/runtime_state.py`, which always resets to disarmed on restart). `resolve_mode()` is called fresh on every `place_order()` — the strategy code never branches on mode, exactly per spec §35's hard requirement. **No changes needed here; OFAO's TradeIntent → DECISION_CREATED path already inherits this for free.**

## 14. Existing position manager

**No shared/global position registry exists.** Each strategy (`manual_trading`, `cas_dislocation`) keeps its own `self.positions: Dict[str, ...]` and monitors it independently via `MARKET_TICK` polling. `RiskState.open_positions` (the counter `check_open_positions` in `risk_limits.py` checks against `max_open_positions=3`) **is never incremented or decremented anywhere in the codebase** — confirmed by repository-wide search. This limit is currently a no-op; it always passes. **OFAO's own state machine (with `setup_id`) must be the real safeguard against duplicate/concurrent positions per instrument** — the shared risk engine cannot be relied on for this today.

## 15. Existing risk manager

`backend/app/execution/risk_limits.py` — pure, tested, real gates: `check_kill_switch`, `check_market_hours`, `check_quantity`, `check_open_positions` (currently a no-op per §14), `check_daily_loss`, `check_daily_order_count`, plus the `source`-specific extras (`evaluate_algo_extra` for ALGO/MANUAL, `check_cas_enabled` for CAS_DISLOCATION). `RiskEngine.halt(reason)`/`.resume()` is the kill-switch trip lever (spec §43). **Reusable as-is; OFAO needs one new `elif source == "OFAO":` branch, mirroring CAS_DISLOCATION's — see §10.**

## 16. Existing SL/target manager

No shared SL/target monitor. Each strategy manages its own exits by polling `MARKET_TICK` against its own stored stop/target (see `manual_trading/engine.py`'s `_check_positions`, `cas_dislocation/engine.py`'s `_close_position`). OFAO's thesis-based exit (spec §26) will follow this same per-strategy-owned pattern — there is no shared infrastructure to plug into for exit monitoring, only a proven pattern to copy.

## 17. Existing UI

`frontend/src/views/` + `components/` — every live strategy gets a dedicated view (e.g. `ExpiryReversalView.tsx`, `PullbackChopFilterView.tsx`) fed by a Zustand store + WebSocket hook reading its own `ws/{channel}`, registered in `ConnectionManager` (`api/websockets.py`). This is a proven, repeatable pattern — OFAO's dashboard (spec §28/§29) follows it exactly: new `useOFAOStore`, `useOFAOWebSocket`, `OFAOView.tsx`, a new `"ofao"` WS channel.

## 18. Existing alerts

No dedicated alerts/notifications system exists (no toast/push/webhook infra found). Each strategy's WebSocket state stream *is* its de facto alert mechanism today (the frontend renders state transitions as they arrive). OFAO's alert list (spec §30) would be new state-transition events on its own channel, following the same convention — not a new alerting subsystem.

## 19. Existing database/logging

`backend/app/workers/persistence.py` — DuckDB-backed (`analytics.duckdb`), event-driven (`event_bus.subscribe("persist_execution", ...)` etc.), batched inserts every 1s/100 events. Existing tables: `risk_events`, `executions` (both generic: instrument/action/status only), `order_flow_snapshots`. **None of these tables can hold OFAO's rich trade-journal fields** (setup_id, absorption_strength, score, location, Fib level, imbalance %, R-multiple, etc. — spec §27). A new table + a new `persist_ofao_setup`/`persist_ofao_trade` event, following the exact same worker pattern, is needed.

## 20. Existing strategy framework

The de facto convention across every strategy in `backend/app/strategies/`: a class with `start()`/`stop()`, `event_bus.subscribe("CANDLE_CLOSED"/"MARKET_TICK"/"trending_oi", ...)`, a per-instrument state dict, started/stopped in `main.py`'s startup/shutdown handlers. No formal base class or interface exists — every strategy is independently written following this shared shape by convention, not enforced by inheritance. OFAO should follow the same convention (no new "strategy framework" to build).

---

## 21. Exact integration point for OFAO

```
OFAOEngine (new, backend/app/strategies/order_flow_absorption/)
  subscribes to: CANDLE_CLOSED, MARKET_TICK, trending_oi, footprint_candles
  runs: Context → Location → Absorption → Dominance → Confirmation → Option Selection
  produces: TradeIntent (internal dataclass/pydantic model)
       ↓
  resolves real instrument_token + quantity (via option_chain_client + lot_sizes,
  mirroring cas_dislocation/engine.py's _open_position)
       ↓
  event_bus.publish("DECISION_CREATED", {... source: "OFAO", instrument_token, quantity, price ...})
       ↓
  RiskEngine.process_decision()  — existing, unchanged, minus one new elif branch
       ↓ (if approved)
  EXECUTION_REQUEST → ExecutionEngine → order_gateway.place_order()
       ↓
  resolve_mode() — existing, unchanged — decides DRY_RUN / SANDBOX / LIVE
```

New risk_limits.py additions required (mirroring CAS_DISLOCATION exactly):
- `OFAOConfig` (pydantic model: `enabled`, `absorption_strength_threshold`, `imbalance_ratio_pct`, `signal_timeout_seconds`, `max_spread_pct`, `risk_per_trade_pct`, `max_entry_time`, ...)
- `check_ofao_enabled(config: OFAOConfig) -> Optional[str]`
- one new branch in `RiskEngine.process_decision()`: `elif source == "OFAO": ...`

This keeps OFAO's capital/position sizing fully independent of the single-underlying `algo_config_state` (MANUAL mode) budget, which is the right call since OFAO trades NIFTY *and* SENSEX concurrently.

---

## 22. Files proposed to create (none written yet)

**Backend — strategy core (new package `backend/app/strategies/order_flow_absorption/`)**
- `models.py` — state enums (§10 of spec), `TradeIntent`, `SetupContext`, `OFAOConfig`
- `context.py` — 1H/4H structure classification (pure functions, testable)
- `location.py` — value-structure + Fibonacci + location classification (pure functions)
- `volume_profile.py` — **new**: POC/VAH/VAL/HVN/LVN computation from candle history (does not exist anywhere today)
- `absorption.py` — absorption detection + `absorption_strength` scoring, built on `FootprintCandle`
- `dominance.py` — dominance-shift + microstructure-break confirmation, built on `check_diagonal_imbalance`/`check_stacked_imbalance`
- `option_selection.py` — ATM/ITM candidate scoring using `option_chain_client` + `greeks.BlackScholes` + `lot_sizes`
- `engine.py` — `OFAOEngine`: the state machine (§10), tick/candle ingestion, `TradeIntent` → `DECISION_CREATED` bridge
- `state_machine.py` — the explicit state machine + `setup_id` generation/dedup

**Backend — risk integration**
- `backend/app/execution/risk_limits.py` — add `OFAOConfig` reference, `check_ofao_enabled`
- `backend/app/engines/risk.py` — one new `elif source == "OFAO":` branch
- `backend/app/api/endpoints/ofao.py` — config get/set + live state REST endpoints (mirrors `cas_dislocation.py`'s endpoint file)

**Backend — persistence**
- `backend/app/workers/persistence.py` — new `ofao_setups`/`ofao_trades` tables + `persist_ofao_setup`/`persist_ofao_trade` subscriptions

**Backend — wiring**
- `backend/app/main.py` — import + start/stop `ofao_engine`, include `ofao_router`
- `backend/app/api/websockets.py` — new `"ofao"` channel + `event_bus.subscribe("ofao_state", ...)`

**Frontend**
- `frontend/src/stores/useOFAOStore.ts`, `hooks/useOFAOWebSocket.ts`, `views/OFAOView.tsx` (dashboard per spec §28/§29), sidebar entry

**Tests** — one file per backend module above, following this session's established pattern (pure-function unit tests + integration tests against synthetic candle/footprint fixtures, no live broker calls).

## 23. Potential risks

1. **No real futures depth feed exists.** OFAO's absorption/imbalance detection is meaningless without real Level-2 data on NIFTY/SENSEX/BANKNIFTY futures. Running OFAO against the current mock feed would generate `DECISION_CREATED` events from simulated randomness if wired end-to-end without a clear gate — **OFAO must refuse to arm for LIVE/real decisions while its underlying data source is the mock feed**, and this needs a hard, unambiguous data-source check, not a config flag someone can forget.
2. **VWAP is silently inert on live data** (§3/§7) — any VWAP-confluence check in the Location Engine will always see `None` on real ticks today unless the futures feed carries real volume.
3. **`max_open_positions` risk check is a no-op** (§14) — cannot be relied on as a safety net; OFAO's own setup/position tracking is load-bearing here, not a backstop.
4. **Option bid/ask/Greeks extraction is unverified** — spec's liquidity/spread/freshness checks (§13, §17, §24) assume data that may not currently be parsed out of the raw Upstox response.
5. **No broker position/order reconciliation exists anywhere** (spec §41) — this would be new capability for the whole app, not just OFAO, and touches the shared `order_gateway`/broker auth layer more than the strategy itself.
6. **1H/4H context, Fibonacci, and volume profile are all new math** — the biggest implementation surface, and the part most in need of careful, honest backtesting before any LIVE arming, per the spec's own "no trade is a valid output" philosophy.

## 24. Missing data (must be built, not reused)

- Real Level-2 depth subscription for NIFTY/SENSEX/BANKNIFTY futures (Upstox `full`/`full_d30` mode)
- Volume profile / POC / VAH / VAL / HVN / LVN engine
- 1H/4H market structure (HH/HL/LH/LL) classifier
- Fibonacci retracement calculator
- Swing high/low detector beyond the "simplistic" one in `trending_oi_price_action`
- Option bid/ask/Greeks extraction from the live option chain (verify Upstox response shape first)
- Trading-day/holiday calendar (only intraday time-of-day phase exists)
- Broker position/order reconciliation on startup
- India VIX feed, GEX approximation
