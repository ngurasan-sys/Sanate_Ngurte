import { create } from 'zustand';
import type { Strategy } from '../mock/interfaces';
import { mockStrategies } from '../mock/data';

interface StrategyState {
  strategies: Strategy[];
  setStrategies: (strategies: Strategy[]) => void;
  updateStrategyPnl: (id: string, pnl: number) => void;
}

export const useStrategyStore = create<StrategyState>((set) => ({
  strategies: mockStrategies,
  setStrategies: (strategies) => set({ strategies }),
  updateStrategyPnl: (id, pnl) =>
    set((state) => ({
      strategies: state.strategies.map((strat) =>
        strat.id === id ? { ...strat, pnl } : strat
      ),
    })),
}));
