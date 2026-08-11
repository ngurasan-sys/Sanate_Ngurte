import { create } from 'zustand';
import type { MarketIndex } from '../mock/interfaces';
import { mockMarketIndices } from '../mock/data';

interface MarketState {
  indices: Record<'NIFTY' | 'SENSEX', MarketIndex>;
  selectedSymbol: 'NIFTY' | 'SENSEX';
  timeframe: '5m' | '15m' | '30m' | '1h' | 'Daily';
  setIndices: (indices: Record<'NIFTY' | 'SENSEX', MarketIndex>) => void;
  updateIndexPrice: (symbol: 'NIFTY' | 'SENSEX', price: number, change: number, percent: number) => void;
  setSelectedSymbol: (symbol: 'NIFTY' | 'SENSEX') => void;
  setTimeframe: (timeframe: '5m' | '15m' | '30m' | '1h' | 'Daily') => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  indices: mockMarketIndices,
  selectedSymbol: 'NIFTY',
  timeframe: '15m',
  setIndices: (indices) => set({ indices }),
  updateIndexPrice: (symbol, price, change, percent) =>
    set((state) => ({
      indices: {
        ...state.indices,
        [symbol]: {
          ...state.indices[symbol],
          spot: price,
          change: change,
          changePercent: percent,
        },
      },
    })),
  setSelectedSymbol: (selectedSymbol) => set({ selectedSymbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
}));
