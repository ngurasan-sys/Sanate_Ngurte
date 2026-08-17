import { create } from 'zustand';

// Matches GET /api/v1/strategies' actual response shape
// (backend/app/api/endpoints/strategies.py) — not the old mock/interfaces.ts
// Strategy type, which expected fields (indicators/levels/oi/historicalStats)
// the backend never sends and was missing fields it does send
// (executionMode/tradingMode/blockedReason).
export type ExecutionMode = 'DISABLED' | 'PAPER' | 'ALGO';
export type TradingMode = 'AUTO' | 'MANUAL';

export interface Strategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  status: string;
  executionMode: ExecutionMode;
  tradingMode: TradingMode;
  blockedReason: string | null;
  signal: string | null;
  confidence: number | null;
  pnl: number | null;
  tradeCount: number;
  winRate: string | null;
  readiness: string;
}

interface StrategyState {
  strategies: Strategy[];
  setStrategies: (strategies: Strategy[]) => void;
  updateStrategyPnl: (id: string, pnl: number) => void;
}

export const useStrategyStore = create<StrategyState>((set) => ({
  strategies: [],
  setStrategies: (strategies) => set({ strategies }),
  updateStrategyPnl: (id, pnl) =>
    set((state) => ({
      strategies: state.strategies.map((strat) =>
        strat.id === id ? { ...strat, pnl } : strat
      ),
    })),
}));
