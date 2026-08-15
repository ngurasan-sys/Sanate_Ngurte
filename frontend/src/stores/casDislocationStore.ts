import { create } from 'zustand';

export type CASState = 'PRE_CAS' | 'CAS_FREEZE' | 'DISLOCATION' | 'VOLATILITY_SHOCK' | 'SIGNAL' | 'INACTIVE';
export type CASSignal = 'NONE' | 'BUY_CE' | 'BUY_PE';

export interface CASReading {
  timestamp: string;
  state: CASState;
  frozen_spot: number | null;
  future_price: number | null;
  future_displacement: number | null;
  future_velocity: number | null;
  atm_strike: number | null;
  ce_bid: number | null;
  ce_ask: number | null;
  ce_theoretical: number | null;
  ce_dislocation_pct: number | null;
  pe_bid: number | null;
  pe_ask: number | null;
  pe_theoretical: number | null;
  pe_dislocation_pct: number | null;
  iv_shift_ce: number | null;
  iv_shift_pe: number | null;
  volume_acceleration: number | null;
  score: number;
  signal: CASSignal;
  reason: string;
}

export interface CASConfig {
  underlying: string;
  enabled: boolean;
  lots: number;
  max_hold_seconds: number;
  min_score_to_alert: number;
  min_score_to_execute: number;
  auto_execute: boolean;
  updated_at: string | null;
}

export interface CASPosition {
  position_id: string;
  underlying: string;
  option_type: 'CE' | 'PE';
  strike: number;
  instrument_token: string;
  lots: number;
  quantity: number;
  entry_price: number;
  max_hold_seconds: number;
  status: 'PENDING' | 'OPEN' | 'CLOSED';
  created_at: string;
  opened_at: string | null;
  closed_at: string | null;
  exit_reason: string | null;
  last_ltp: number | null;
}

interface CASDislocationState {
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';
  reading: CASReading | null;
  config: CASConfig | null;
  positions: CASPosition[];

  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
  setReading: (reading: CASReading) => void;
  setConfig: (config: CASConfig) => void;
  setPositions: (positions: CASPosition[]) => void;
}

export const useCASDislocationStore = create<CASDislocationState>((set) => ({
  connectionStatus: 'DISCONNECTED',
  reading: null,
  config: null,
  positions: [],

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setReading: (reading) => set({ reading }),
  setConfig: (config) => set({ config }),
  setPositions: (positions) => set({ positions }),
}));
