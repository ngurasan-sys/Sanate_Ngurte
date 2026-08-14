import { create } from 'zustand';
import type { OptionChainData, SpotTrendingOIItem, FutureTrendingOIItem } from '../mock/interfaces';
import { mockOptionChains } from '../mock/data';

interface OptionState {
  wsConnected: boolean;
  optionChains: Record<'NIFTY' | 'SENSEX', OptionChainData[]>;
  spotTrendingOI: Record<'NIFTY' | 'SENSEX', SpotTrendingOIItem[]>;
  futureTrendingOI: Record<'NIFTY' | 'SENSEX', FutureTrendingOIItem[]>;
  selectedExpiry: string;
  strikeRange: number; // e.g. 5 strikes to show
  setOptionChains: (chains: Record<'NIFTY' | 'SENSEX', OptionChainData[]>) => void;
  updateLtp: (symbol: 'NIFTY' | 'SENSEX', strike: number, type: 'ce' | 'pe', newLtp: number) => void;
  setSelectedExpiry: (expiry: string) => void;
  setStrikeRange: (range: number) => void;
  startWsLiveFeed: () => void;
}

let ws: WebSocket | null = null;

export const useOptionStore = create<OptionState>((set, get) => ({
  wsConnected: false,
  optionChains: mockOptionChains,
  spotTrendingOI: { NIFTY: [], SENSEX: [] }, // Using empty arrays to ensure real data populates it
  futureTrendingOI: { NIFTY: [], SENSEX: [] },
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
  startWsLiveFeed: () => {
    if (ws) return;
    const wsUrl = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000') + '/ws/trending_oi';
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      set({ wsConnected: true });
    };

    ws.onclose = () => {
      set({ wsConnected: false });
      ws = null;
      // Reconnect logic
      setTimeout(() => get().startWsLiveFeed(), 3000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'tick_update') {
          const view = payload.view;
          const underlying = payload.underlying as 'NIFTY' | 'SENSEX';
          const row = payload.row;

          if (view === 'spot_trending_oi') {
            set((state) => {
              const currentList = state.spotTrendingOI[underlying] || [];
              return {
                spotTrendingOI: {
                  ...state.spotTrendingOI,
                  [underlying]: [row, ...currentList].slice(0, 50) // Keep latest 50
                }
              };
            });
          } else if (view === 'future_trending_oi') {
            set((state) => {
              const currentList = state.futureTrendingOI[underlying] || [];
              return {
                futureTrendingOI: {
                  ...state.futureTrendingOI,
                  [underlying]: [row, ...currentList].slice(0, 50)
                }
              };
            });
          }
        }
      } catch (err) {
        console.error("Failed to parse trending oi WS message", err);
      }
    };
  }
}));
