import { create } from 'zustand';
import type { OptionChainData, SpotTrendingOIItem, FutureTrendingOIItem } from '../mock/interfaces';
import { mockOptionChains, mockSpotTrendingOI, mockFutureTrendingOI } from '../mock/data';

interface OptionState {
  optionChains: Record<'NIFTY' | 'SENSEX', OptionChainData[]>;
  spotTrendingOI: Record<'NIFTY' | 'SENSEX', SpotTrendingOIItem[]>;
  futureTrendingOI: Record<'NIFTY' | 'SENSEX', FutureTrendingOIItem[]>;
  selectedExpiry: string;
  strikeRange: number; // e.g. 5 strikes to show
  setOptionChains: (chains: Record<'NIFTY' | 'SENSEX', OptionChainData[]>) => void;
  updateLtp: (symbol: 'NIFTY' | 'SENSEX', strike: number, type: 'ce' | 'pe', newLtp: number) => void;
  setSelectedExpiry: (expiry: string) => void;
  setStrikeRange: (range: number) => void;
}

export const useOptionStore = create<OptionState>((set) => ({
  optionChains: mockOptionChains,
  spotTrendingOI: mockSpotTrendingOI,
  futureTrendingOI: mockFutureTrendingOI,
  selectedExpiry: '2026-08-20',
  strikeRange: 5,
  setOptionChains: (optionChains) => set({ optionChains }),
  updateLtp: (symbol, strike, type, newLtp) =>
    set((state) => {
      const chainList = state.optionChains[symbol];
      const updatedChains = chainList.map((chain) => ({
        ...chain,
        strikes: chain.strikes.map((s) => {
          if (s.strike === strike) {
            return {
              ...s,
              [type]: {
                ...s[type],
                ltp: newLtp,
              },
            };
          }
          return s;
        }),
      }));
      return {
        optionChains: {
          ...state.optionChains,
          [symbol]: updatedChains,
        },
      };
    }),
  setSelectedExpiry: (selectedExpiry) => set({ selectedExpiry }),
  setStrikeRange: (strikeRange) => set({ strikeRange }),
}));
