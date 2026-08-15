import { create } from 'zustand';

export interface AlgoTradingConfig {
  mode: 'SYSTEM' | 'MANUAL';
  enabled: boolean;
  underlying: string | null;
  capital: number | null;
  lot_schedule: number[];
  stop_loss_pct: number | null;
  target_pct: number | null;
  updated_at: string | null;
}

interface AlgoConfigState {
  config: AlgoTradingConfig | null;
  setConfig: (config: AlgoTradingConfig) => void;
}

export const useAlgoConfigStore = create<AlgoConfigState>((set) => ({
  config: null,
  setConfig: (config) => set({ config }),
}));
