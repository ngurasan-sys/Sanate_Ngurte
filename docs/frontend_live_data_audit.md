# Frontend Live Data Audit — Post-Migration (verified against commit 2bd32bd)

**Audit date:** 2026-08-17
**Method:** Independent read-only re-verification (does not trust the migration's own summary — every claim below is grep/read-confirmed against current source)

---

## Verdict

The 5 target stores (`marketStore`, `decisionStore`, `riskStore`, `strategyStore`, `optionStore`) are genuinely clean — no mock imports, all initialize empty/null, and each is paired with an actually-invoked live-fetch hook (`useLiveMarketIndices`/`useLiveDecisions`/`useLiveRisk`/`useLiveStrategies` are all called in `App.tsx:56,59,62,65`, not just defined). **That specific claim from the migration holds.**

But the broader claim of "removing mock-data dependencies" is only partially true:

- One local mock array survives in production (`OpenHighTable.tsx`), live on the ALGO_DASHBOARD page
- 13 additional hardcoded-literal-as-live-data spots exist outside the named-mock grep surface, across 6+ pages
- Two dead-wiring bugs (`useAlgoWebSocket` never invoked, `twoCandleStore` never fed) leave 4 pages permanently starved of data they present as live/dynamic

---

## Exact Counts

| Metric | Count |
|---|---|
| Total pages audited | 40 |
| LIVE | 22 |
| PARTIAL | 12 |
| MOCK | 5 |
| STATIC | 1 |
| Production mock-import/mock-symbol occurrences remaining (grep-verified) | **1** (`OpenHighTable.tsx` local `mockSignals`) |
| `mock/data.ts` named exports with production imports | **0 of 10** |
| `Math.random(` in production code | 0 |
| Additional hardcoded-literal-as-live-data spots (beyond named-mock grep) | 13 |
| Dead-wiring bugs (hook/store defined but never invoked) | 2 (`useAlgoWebSocket`, `twoCandleStore`) |

---

## Part 1 — Mock Data Audit

### 1a. Named mock symbols

| File:Line | Context |
|---|---|
| `frontend/src/mock/data.ts:14,43,122,139,156,224,265,310,333,349` | Definitions of all 10 named mock exports (not production usage) |
| `frontend/src/stores/marketStore.test.ts`, `portfolioStore.test.ts`, `optionStore.test.ts` | Test-only — excluded |
| **`frontend/src/components/open_high/OpenHighTable.tsx:17-39,62`** | **PRODUCTION.** Locally-declared `const mockSignals: OHSignal[] = [...]` (2 hardcoded rows, fake `entryPrice: 24500.5` etc.), rendered directly in JSX. Reachable live via `ALGO_DASHBOARD` (`AlgoDashboardView.tsx:1,325`). |

No `Math.random(` exists anywhere in `frontend/src`. The only client-side randomness is `crypto.getRandomValues` in `useLiveFeedSimulator.ts`, used only to jitter a displayed WS-latency number (explicitly commented as UI-only, not market data).

**All 10 named mock exports of `mock/data.ts` have zero production imports.**

### 1b. Hardcoded literals presented as live data (not named-mock symbols, found separately)

| File:Line | Context |
|---|---|
| `App.tsx:210-212` | `MetricCard mock` "Available Margin" `₹4,82,500` on DASHBOARD |
| `App.tsx:230-252` | DASHBOARD "Top Performing Strategy" card — fully hardcoded (`"15-Min Breakout"`, `"78%"`, `"64.5% (124 trades)"`) |
| `App.tsx:317-332` | TECHNICAL page — 6 fully hardcoded indicator values (EMA/RSI/MACD/ATR/Supertrend/Bollinger) |
| `App.tsx:349-367` | QUANT page — hardcoded Z-score/Sharpe/Sortino/SNR values |
| `App.tsx:397-412` | LIVE_SIGNALS page — hardcoded 3-row "Intraday Strategy Triggers" array |
| `App.tsx:439-442` | PNL page — 4 `MetricCard mock` values (Realized/Unrealized MTM, Charges, Net Return %) |
| `components/GreeksPanel.tsx:6-22` | Hardcoded `greeks` array (Delta/Gamma/Theta/Vega) and hardcoded 7-point `ivData` series, labeled "Real-time" |
| `components/GapOpeningStrategyPanel.tsx:11` | `const previousClose = 24450.0;` hardcoded |
| `components/GapOpeningStrategyPanel.tsx:67-105` | "Market Intelligence" card fully hardcoded (Diff OI, Net PCR, VWAP, SuperTrend, ATR, etc.) |
| `components/ChartPanel.tsx:118-148` | Overlay labels derived from `baseValue ± constant`, plus flat hardcoded `"OI Bullish Ratio: 1.14"` and `"VOL: 1.2M Contracts"` |
| `components/DetailDrawer.tsx:56,60,68` | Fabricates `decision.confidence * 1.15`, `decision.conflictScore * 0.8`, and a flat hardcoded `"1.2x max"` — fields not in the real `Decision` payload |
| `components/InteractiveChart.tsx:92-98` | "SmartTrend SL" series computed client-side as `d.low - 10` per candle — fabricated indicator drawn over real live candles |

---

## Part 2 — Page-by-Page Audit (40 pages)

| # | Page | Data source | REST endpoint | WS channel | Mock dependency | Status |
|---|---|---|---|---|---|---|
| 1 | DASHBOARD | marketStore/portfolioStore/decisionStore | `/api/v1/market/indices` | — | App.tsx:210-252 mock margin card + hardcoded strategy card | PARTIAL |
| 2 | ALGO_DASHBOARD | algoStore/systemStore | `/api/v1/algo/engine/status`, `/execution/mode` | `/ws/algo` defined but **never invoked** | OpenHighTable mockSignals; algoStore.strategies/signals/pipelineMetrics/riskMetrics permanently static (dead hook) | PARTIAL |
| 3 | MARKET_NIFTY | marketStore + useLiveLevels | `/api/v1/market/indices`, `/levels/{i}` | — | none | LIVE |
| 4 | MARKET_SENSEX | same | same | — | none | LIVE |
| 5 | INTERACTIVE_CHART | useChartWebSocket + REST history | `/api/v1/chart/history` | chart WS | fabricated "SmartTrend" (`low-10`) | PARTIAL |
| 6 | SPOT_OI | optionStore.spotTrendingOI | — | `/ws/trending_oi` | none | LIVE |
| 7 | FUTURE_OI | optionStore.futureTrendingOI | — | `/ws/trending_oi` | none | LIVE |
| 8 | OPTION_CHAIN | optionStore.optionChains | `/api/v1/option-chain*` (backend placeholder) | — | no fake data shown, but no live source exists | MOCK (placeholder) |
| 9 | GREEKS | none | — | — | fully hardcoded greeks + IV chart | MOCK |
| 10 | OPTION_ANALYTICS | optionAnalyticsStore | — | `/ws/option_analytics` | none | LIVE |
| 11 | LEVELS | useLiveLevels | `/api/v1/levels/{i}` | — | none | LIVE |
| 12 | TECHNICAL | none | — | — | fully hardcoded indicator array | MOCK |
| 13 | ORDER_FLOW | useFootprintStore | write-only ratio endpoint | `/ws/footprint` | backend feed disclosed as simulated random-walk (banner) | PARTIAL |
| 14 | QUANT | none | — | — | fully hardcoded metrics | MOCK |
| 15 | STRATEGY_MONITOR | strategyStore | `/api/v1/strategies` (**registry never populated — see integration audit**) | — | none directly, but endpoint always returns empty | LIVE (wiring correct, data empty pending backend fix) |
| 16 | GAP_OPENING_STRATEGIES | marketStore (partial) | — | — | hardcoded previousClose + full "Market Intelligence" block | MOCK |
| 17 | THREE_MINUTE_GAP | threeMinuteGapStore | — | none wired (TODO) | none rendered — honest NO DATA state, but unimplemented | STATIC (honest placeholder) |
| 18 | LIVE_SIGNALS | none | — | — | fully hardcoded signal list | MOCK |
| 19 | BACKTEST | local state | `/api/v1/backtest/*` | — | none (discloses simulated fills) | LIVE |
| 20 | PULLBACK_CHOP_FILTER | useChopFilterStore | — | `/ws/pullback_chop` | none | LIVE |
| 21 | DECISION_INTEL | decisionStore | `/api/v1/decisions` | — | DetailDrawer fabricates Signal Score/Conflict Ratio/Leverage | PARTIAL |
| 22 | POSITIONS | useLivePositions | `/api/v1/manual-trading/positions`, `/cas-dislocation/positions` | — | none | LIVE |
| 23 | ORDERS | useLiveOrders | `/api/v1/executions` | — | none | LIVE |
| 24 | PNL | portfolioStore + hardcoded cards | — | — | 4 mock MetricCards | PARTIAL |
| 25 | RISK | riskStore | `/api/v1/risk/summary` | — | none | LIVE |
| 26 | UPSTOX | systemStore | `/api/v1/broker/upstox/login` | — | none | LIVE |
| 27 | SYSTEM_HEALTH | none | — | — | fully hardcoded telemetry | MOCK |
| 28 | DATA_FEED | marketStore | — | — | static timestamp label, harmless "UNAVAILABLE" placeholder | PARTIAL |
| 29 | TRENDING_OI_PA | marketStore, algoStore.signals | — | (algoStore signals dead — see #2) | latestSignal always undefined, shows fallback zeros | PARTIAL |
| 30 | TRENDING_OI_CROSSOVER | optionStore.spotTrendingOI | — | `/ws/trending_oi` | none | LIVE |
| 31 | STRADDLE | straddleStore | — | `/ws/straddle` | none | LIVE |
| 32 | INTRADAY_TREND_SCALPER | marketStore, algoStore.signals | — | (dead, see #2) | same dead-signal fallback | PARTIAL |
| 33 | MARKET_BREADTH | local state | — | `/ws/market_breadth` | none | LIVE |
| 34 | TWO_CANDLE | twoCandleStore | — | **none wired at all** — setConditions/setSignalData never called anywhere | frozen at hardcoded initial state forever | MOCK (dead store) |
| 35 | EXPIRY_REVERSAL | local state | — | `/ws/expiry_reversal` | none | LIVE |
| 36 | EXPIRY_TRACKER | local state | — | `/ws/expiry_tracker` | none | LIVE |
| 37 | EXECUTION_CONTROL | local state | `/api/v1/execution/*` | — | none | LIVE |
| 38 | BROKER_CONNECTIONS | local state | `/api/v1/brokers*` | — | none | LIVE |
| 39 | CAS_DISLOCATION | casDislocationStore | `/api/v1/cas-dislocation/*` | `/ws/cas_dislocation(_positions)` | none | LIVE |
| 40 | OFAO | useOFAOStore | `/api/v1/ofao/*` | `/ws/ofao` | backend feed disclosed as simulated (banner) | PARTIAL |

`AlgoTradingConfigPanel`/`ManualTradingPanel` (rendered inside row 2) are themselves fully live — row 2's PARTIAL rating is driven specifically by the dead `useAlgoWebSocket` hook and `OpenHighTable`'s mock array.

---

## Comparison to Pre-Migration Baseline

| Status | Before (Phase 1 audit) | After (this audit) | Delta |
|---|---|---|---|
| LIVE | 17 | 22 | +5 |
| PARTIAL | 9 | 12 | +3 |
| MOCK | 13 | 5 | -8 |
| STATIC | 2 | 1 | -1 (THREE_MINUTE_GAP reclassified as honest placeholder) |

Note: PARTIAL count went up, not down — this is expected and correct. Several pages that were previously flat MOCK (e.g. TRENDING_OI_PA, INTRADAY_TREND_SCALPER, DASHBOARD) now have a genuine live component (marketStore) sitting alongside a still-hardcoded one (the algoStore.signals dead-hook, or a mock MetricCard), which correctly reclassifies them from MOCK → PARTIAL rather than jumping straight to LIVE.

---

## Newly Identified Issues (not caught by the original migration)

1. **`OpenHighTable.tsx`** — local `mockSignals` array, not from `mock/data.ts`, so it wasn't caught by the original "remove mock/data.ts imports" scope. Still production-visible on ALGO_DASHBOARD.
2. **`useAlgoWebSocket` is defined but never invoked anywhere** — breaks ALGO_DASHBOARD, TRENDING_OI_PA, and INTRADAY_TREND_SCALPER (all read `algoStore.signals`, which nothing ever populates).
3. **`twoCandleStore` has zero live wiring** — `setConditions`/`setSignalData` are never called outside tests. TWO_CANDLE page is frozen at its hardcoded initial state indefinitely.
4. **13 hardcoded-literal-as-live-data spots** outside the named-mock grep surface (see Part 1b) — these were never flagged because they don't reference `mock/data.ts` symbols by name.
