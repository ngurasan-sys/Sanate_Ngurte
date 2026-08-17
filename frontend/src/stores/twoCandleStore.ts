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

// No backend strategy engine for "two_candle" is registered or started
// anywhere in backend/app/main.py, and setConditions/setSignalData are
// never called outside tests — there is currently no live data source
// for this page at all. Defaults reflect that honestly (no conditions
// claimed met, no fabricated "MONITORING" activity) rather than looking
// like an idle-but-live system.
export const useTwoCandleStore = create<TwoCandleState>((set) => ({
  conditions: {
    volumeSpike: false,
    indicatorAlignment: false,
    momentumRoom: false,
    trendingOi: false,
  },
  signalData: {
    status: 'PAUSED',
    signal: 'NONE',
    reason: 'NO DATA — no backend strategy engine is connected for this page yet.',
  },

  setConditions: (updates) =>
    set((state) => ({ conditions: { ...state.conditions, ...updates } })),

  setSignalData: (updates) =>
    set((state) => ({ signalData: { ...state.signalData, ...updates } })),
}));
