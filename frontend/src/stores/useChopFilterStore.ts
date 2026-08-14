import { create } from 'zustand';

export interface SignalData {
  type: string;
  message: string;
  color: string;
}

export interface ChopFilterState {
  timestamp: string | null;
  symbol: string | null;
  priceData: {
    ltp: number;
    vwap: number;
    supertrend: number;
    upperBand: number;
    lowerBand: number;
  } | null;
  oiData: {
    diffPct: number;
  } | null;
  marketState: 'CHOP_ZONE' | 'TRENDING_BULLISH' | 'TRENDING_BEARISH' | null;
  internalState: string | null;
  activeSignal: SignalData | null;
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';

  updateState: (data: Partial<ChopFilterState>) => void;
  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
}

export const useChopFilterStore = create<ChopFilterState>((set) => ({
  timestamp: null,
  symbol: null,
  priceData: null,
  oiData: null,
  marketState: null,
  internalState: null,
  activeSignal: null,
  connectionStatus: 'DISCONNECTED',

  updateState: (data) => set((state) => ({ ...state, ...data })),
  setConnectionStatus: (status) => set({ connectionStatus: status })
}));
