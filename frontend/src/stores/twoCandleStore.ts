import { create } from 'zustand';

export interface TwoCandleCondition {
  volumeSpike: boolean;
  indicatorAlignment: boolean;
  momentumRoom: boolean;
  trendingOi: boolean;
}

export interface TwoCandleSignal {
  status: 'PAUSED' | 'MONITORING' | 'SIGNAL_ACTIVE';
  signal: 'NONE' | 'BUY_CALL' | 'BUY_PUT';
  entryTrigger?: string;
  stopLoss?: number;
  reason: string;
  currentPrice?: number;
}

interface TwoCandleState {
  conditions: TwoCandleCondition;
  signalData: TwoCandleSignal;

  // Actions for mock testing or real updates
  setConditions: (conditions: Partial<TwoCandleCondition>) => void;
  setSignalData: (data: Partial<TwoCandleSignal>) => void;
}

export const useTwoCandleStore = create<TwoCandleState>((set) => ({
  conditions: {
    volumeSpike: false,
    indicatorAlignment: false,
    momentumRoom: true,
    trendingOi: false,
  },
  signalData: {
    status: 'MONITORING',
    signal: 'NONE',
    reason: 'Awaiting Setup',
  },

  setConditions: (updates) =>
    set((state) => ({ conditions: { ...state.conditions, ...updates } })),

  setSignalData: (updates) =>
    set((state) => ({ signalData: { ...state.signalData, ...updates } })),
}));
