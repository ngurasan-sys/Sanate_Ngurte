import { create } from 'zustand';

interface ThreeMinuteGapState {
  isConnected: boolean;
  strategyStatus: string;
  underlying: string;
  executionMode: string;

  futuresPrice: number;
  threeMinTrend: string;
  superTrend: number;
  vwap: number;
  dayHigh: number;
  dayLow: number;

  gapType: string;
  gapBase: number;
  gapTop: number;
  gapStatus: string;

  diffOi: number;
  diffOiPercent: number;
  strengthDots: number;
  sentiment: string;

  pullbackStatus: string;
  superTrendInteraction: string;
  fvgInteraction: string;
  entryStatus: string;

  lots: number;
  entryPrice: number;
  avgPrice: number;
  stopLoss: number;
  unrealizedPnl: number;

  signalAction: string;
  signalReason: string;
  signalTime: string;

  setConnected: (status: boolean) => void;
  updateState: (data: Partial<ThreeMinuteGapState>) => void;
}

export const useThreeMinuteGapStore = create<ThreeMinuteGapState>((set) => ({
  isConnected: false,
  strategyStatus: 'NO DATA',
  underlying: 'NIFTY',
  executionMode: 'DATA_ONLY',

  futuresPrice: 0,
  threeMinTrend: '--',
  superTrend: 0,
  vwap: 0,
  dayHigh: 0,
  dayLow: 0,

  gapType: '--',
  gapBase: 0,
  gapTop: 0,
  gapStatus: '--',

  diffOi: 0,
  diffOiPercent: 0,
  strengthDots: 0,
  sentiment: '--',

  pullbackStatus: '--',
  superTrendInteraction: '--',
  fvgInteraction: '--',
  entryStatus: '--',

  lots: 0,
  entryPrice: 0,
  avgPrice: 0,
  stopLoss: 0,
  unrealizedPnl: 0,

  signalAction: 'WAIT',
  signalReason: '--',
  signalTime: '--',

  setConnected: (status) => set({ isConnected: status }),
  updateState: (data) => set((state) => ({ ...state, ...data })),
}));
