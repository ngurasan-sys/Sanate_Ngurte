import { create } from 'zustand';

export interface OFAOTradeIntent {
  strategy_name: string;
  setup_id: string;
  timestamp: string;
  underlying: string;
  direction: string;
  option_type: 'CE' | 'PE';
  strike: number;
  expiry: string;
  quantity: number;
  underlying_trigger: number;
  underlying_stop: number;
  underlying_target: number;
  risk_reward: number;
  score: number;
  score_max: number;
  confidence: string;
  reason: string;
  location: string;
  absorption_strength: number;
  imbalance_ratio_pct: number;
  market_regime: string;
  volatility_regime: string;
}

export interface OFAOSnapshot {
  instrument_key: string;
  underlying: string;
  timestamp: string;
  state: string;
  setup_id: string | null;
  direction: 'BULL' | 'BEAR' | null;
  location_price: number | null;
  location_reason: string | null;
  absorption_strength: number;
  invalidation_price: number | null;
  trade_intent: OFAOTradeIntent | null;
  last_price: number | null;
}

export interface OFAOConfig {
  enabled: boolean;
  underlyings: string[];
  absorption_strength_threshold: number;
  imbalance_ratio_pct: number;
  risk_reward_min: number;
  entry_start_time: string;
  entry_cutoff_time: string;
  lots: number;
  [key: string]: unknown;
}

interface OFAOState {
  snapshots: Record<string, OFAOSnapshot>;
  config: OFAOConfig | null;
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';

  applySnapshot: (snapshot: OFAOSnapshot) => void;
  setConfig: (config: OFAOConfig) => void;
  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
}

export const useOFAOStore = create<OFAOState>((set) => ({
  snapshots: {},
  config: null,
  connectionStatus: 'DISCONNECTED',

  applySnapshot: (snapshot) => set((state) => ({
    snapshots: { ...state.snapshots, [snapshot.instrument_key]: snapshot },
  })),
  setConfig: (config) => set({ config }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
}));
