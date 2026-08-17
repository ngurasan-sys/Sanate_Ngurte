# Sanate Frontend Live Data Migration — Phase 1 Complete

**Audit Date:** 2026-08-17  
**Scope:** 39 navigable frontend pages, 22 frozen-mock stores/pages, 5 backend endpoint gaps

---

## Executive Summary

Frontend currently shows mock data on **13 MOCK pages** + **9 PARTIAL pages** (mix of live + hardcoded).  
Root cause: **5 frozen-mock stores** have zero live-update callers in production code.

**Critical blocker:** Backend missing **5 essential REST/WS endpoints** needed for migration.  
**High-priority fixes:** 2 stores + 5 UI sections with fake-live badges.

---

## Current State (39 pages)

| Status | Pages | Count |
|--------|-------|-------|
| **LIVE** | Advanced Chart, Market Breadth, OI (Spot/Future), OI Crossover, Option Analytics, Levels, Pullback Chop, Positions, Orders, Execution Control, Broker Connections, Straddle, Expiry Reversal/Tracker, CAS Dislocation, etc. | 17 |
| **PARTIAL** | Dashboard, Algo Dashboard, Market (NIFTY/SENSEX), Order Flow, P&L, Upstox, Trending OI + PA, Intraday Scalper | 9 |
| **MOCK** | Option Chain, Greeks, Strategy Monitor, Gap Opening, 3-Minute Gap (fake-live), Decision Intel, Risk, Data Feed (mislabeled), 2-Candle, Technical, Quant, Live Signals | 13 |
| **STATIC** | Health, Open=High | 2 |

---

## The 5 Frozen Stores

### 1. `marketStore.indices` → `mockMarketIndices`

**File:** `frontend/src/stores/marketStore.ts:446`  
**Mock data:** NIFTY 24500.20, SENSEX 80240.15, etc.  
**Live updater:** `setIndices()` / `updateIndexPrice()` — **NEVER CALLED** in production code outside tests.  
**WebSocket available:** `useLiveFeedSimulator` connects to `/ws/levels` but only updates `systemStore` (latency/status), NOT `marketStore`.

**Affected pages:**
- NIFTY / SENSEX market cards (partial, also have `useLiveLevels` for support/resistance)
- Dashboard summary
- Gap Opening Strategies (hardcoded fallback `previousClose = 24450.0`)
- Trending OI + Price Action (frozen mock + fake "CONNECTED" badge)
- Data Feed (mislabeled "Real-time", shows frozen NIFTY 24500)

**Required backend:**
- `GET /api/v1/market/indices` (fetch NIFTY, SENSEX, BANKNIFTY)
- Response schema: `{ instrument, spot, change, changePercent, vwap, support, resistance, iv, expectedMove, lastUpdate }`

**Alternative:** Subscribe to `/ws/market` channel (already exists in websockets.py but no backend producer yet).

---

### 2. `optionStore.optionChains` → `mockOptionChains`

**File:** `frontend/src/stores/optionStore.ts:714`  
**Mock data:** NIFTY 24500 CE/PE with LTP, bid, ask, OI, IV.  
**Live updaters:** `setOptionChains()` / `updateLtp()` — **NEVER CALLED** in production.  
**WebSocket available:** `/ws/option_analytics` channel exists but is **only for analytics engine**, not chain updates.

**Affected pages:**
- Option Chain page (CRITICAL — frozen entirely)
- Greeks panel (hardcoded manual greeks, not from chain)

**Required backend:**
- `GET /api/v1/option-chain/{instrument}` (fetch all strikes/expirations)
- `GET /api/v1/option-chain/{instrument}/{expiry}` (fetch single expiry)
- Response schema per strike: `{ strike, expiryDate, ce { ltp, bid, ask, oi, volume, iv, greeks }, pe { ... } }`
- Optional: `/ws/option_chain` channel for real-time strike updates (LTP, IV, Greeks).

---

### 3. `strategyStore.strategies` → `mockStrategies`

**File:** `frontend/src/stores/strategyStore.ts:1091`  
**Mock data:** Array of 5 hardcoded strategies with confidence, P&L, win rate.  
**Live updater:** `setStrategies()` — **NEVER CALLED** in production.  
**WebSocket available:** `/ws/algo` channel (consumes SIGNAL_CREATED, STRATEGY_STATUS, etc.) but no centralized "list all strategies" event.

**Affected pages:**
- Strategy Monitor page (frozen entirely at mock)
- Algo Dashboard "Highest Ranked Opportunities" section (hardcoded fallback)

**Required backend:**
- `GET /api/v1/strategies` (list all available strategies with metadata)
- Response schema per strategy: `{ id, name, description, enabled, status, signal, confidence, pnl, tradeCount, winRate, readiness }`
- `/ws/algo` already streams updates — just need initial fetch + optional `/ws/strategies` for registry changes.

---

### 4. `riskStore.riskSummary` → `mockRiskSummary`

**File:** `frontend/src/stores/riskStore.ts:974`  
**Mock data:** availableCapital 1000000, dailyPnl 6240, riskStatus "SAFE", VaR, stress test result.  
**Live updater:** `setRiskSummary()` / `updateRiskMargin()` — **NEVER CALLED** in production.  
**WebSocket available:** `/ws/risk` channel (consumes `risk_passed`/`risk_failed` events).  
**Backend engine:** `RiskEngine` exists and fires events.

**Affected pages:**
- Risk panel page (frozen at mock)

**Required backend:**
- `GET /api/v1/risk/summary` (fetch current risk state)
- Response schema: `{ availableCapital, availableMargin, marginUsed, dailyPnl, dailyLossLimit, exposure, riskStatus, lastUpdate }`
- `/ws/risk` already set up — just need REST endpoint + make RiskEngine publish to websocket.

---

### 5. `decisionStore.decisions` → `mockDecisions`

**File:** `frontend/src/stores/decisionStore.ts:246`  
**Mock data:** Single hardcoded decision "dec-1" with confidence 78, risk "PASSED".  
**Live updater:** `setDecisions()` — **NEVER CALLED** in production.  
**WebSocket available:** `/ws/decisions` channel (consumes `decision_created` events).  
**Backend engine:** `DecisionEngine` exists and fires events.  
**UI import:** `components/DetailDrawer.tsx` directly imports `mockDecisions` (line 3).

**Affected pages:**
- Decision Intel page (frozen at mock)
- DetailDrawer component (hardcoded mock import)

**Required backend:**
- `GET /api/v1/decisions` (fetch decision history + current decisions)
- `GET /api/v1/decisions/{id}` (fetch single decision details)
- Response schema per decision: `{ id, timestamp, strategy, instrument, action, confidence, status, setup_id, riskAssessment }`
- `/ws/decisions` already set up — just need REST endpoint + DecisionEngine must publish to websocket.

---

## 4 High-Priority UI Fixes (Fake-live badges)

| Page | Issue | File:line | Fix |
|------|-------|-----------|-----|
| **3-Minute Gap** | `isConnected: true` hardcoded in useEffect, fakes connection | `components/ThreeMinuteGapPanel.tsx:11` | Wire to actual backend state or remove fake badge |
| **Trending OI + PA** | `status="CONNECTED"` hardcoded literal for "Market" card badge | `views/TrendingOIPAView.tsx:2419` | Make badge reflect real algoStore.signals state |
| **Data Feed** | Page labeled "Real-time" but every field frozen mock (NIFTY 24500, CE 24500 LTP) | `App.tsx:493-519` | Wire to real marketStore.indices + optionStore after endpoints created |
| **Greece Panel** | Hardcoded IV curve (14.10…14.20), Delta 0.52, Gamma 0.0007, Theta -₹2,450, Vega ₹4,120 | `components/GreeksPanel.tsx:7-20` | Wire to real optionStore after chain endpoint created |

---

## Backend Implementation Roadmap

### BLOCKER: 5 Missing Endpoints

**Priority 1 (Required for core frozen stores):**
1. `GET /api/v1/market/indices` — feeds marketStore.indices
2. `GET /api/v1/option-chain/{instrument}` — feeds optionStore.optionChains + Greeks panel
3. `GET /api/v1/decisions` + `GET /api/v1/decisions/{id}` — feeds decisionStore + DetailDrawer
4. `GET /api/v1/risk/summary` — feeds riskStore
5. `GET /api/v1/strategies` — feeds strategyStore

**Priority 2 (Enhancements for existing websockets):**
- Make `/ws/decisions`, `/ws/risk` channels actually publish from DecisionEngine, RiskEngine
- Create `/ws/option_chain` channel for strike LTP/IV updates (optional, or use polling)
- Create `/ws/strategies` channel for strategy registry updates (optional)

---

## Migration Phases (Frontend-side, blocking on backend)

| Phase | Scope | Blocker | Timeline |
|-------|-------|---------|----------|
| **Phase 1** | Audit complete ✓ | None | Done |
| **Phase 2** | Remove production mock imports (App.tsx, DetailDrawer, stores) | Backend endpoints ready | 1-2 days |
| **Phase 3** | Wire marketStore.indices + optionStore.optionChains via REST/WS | Endpoints 1-2 live | 1 day |
| **Phase 4** | Wire riskStore + decisionStore via REST/WS | Endpoints 3-4 live | 1 day |
| **Phase 5** | Wire strategyStore + fix 4 UI fake-live badges | Endpoint 5 live | 0.5 day |
| **Phase 6** | Migrate 9 PARTIAL pages (hardcoded sections in App.tsx) | Phase 5 complete | 1 day |
| **Phase 7** | Final audit + build/test pass | All phases done | 0.5 day |

---

## What's NOT Broken (no changes needed)

✓ `portfolioStore` (positions/orders) — already superseded by `useLivePositions`/`useLiveOrders` (live REST endpoints exist)  
✓ 17 LIVE pages — already wired to real backends  
✓ Order Flow / OFAO pages — simulator correctly disclosed as such  
✓ Tests — can continue using mock data  

---

## Deliverables

After migration:
- ✓ 0 production imports from `mock/data.ts`
- ✓ 13 MOCK pages → LIVE (Option Chain, Greeks, Strategy Monitor, Risk, Decisions, etc.)
- ✓ 9 PARTIAL pages → LIVE (Dashboard, Algo Dashboard, Markets, etc.)
- ✓ 4 fake-live badges removed
- ✓ Build passes, tests pass
- ✓ Final audit doc: `/docs/frontend_live_data_audit_final.md`

---

## Next Step

**BLOCKERS ON BACKEND:**  
Backend team must implement the 5 missing endpoints (Priority 1 above).  
Frontend will begin Phase 2-3 simultaneously if staggered.

**FRONTEND READINESS:**  
Store hookups, import removal, UI badge fixes are ready to merge once endpoints exist.
