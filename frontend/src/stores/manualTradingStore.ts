import { create } from 'zustand';

export interface ManualPosition {
  position_id: string;
  underlying: string;
  option_type: 'CE' | 'PE';
  strike: number;
  instrument_token: string;
  expiry_date: string;
  lots: number;
  quantity: number;
  entry_price: number;
  stop_loss: number;
  target: number;
  pyramid_lot_size: number;
  // PENDING: order submitted, risk/execution outcome not confirmed yet.
  status: 'PENDING' | 'OPEN' | 'CLOSED';
  created_at: string;
  closed_at: string | null;
  exit_reason: string | null;
  last_ltp: number | null;
}

interface ManualTradingState {
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';
  lotSizes: Record<string, number>;
  positions: ManualPosition[];

  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
  setLotSizes: (lotSizes: Record<string, number>) => void;
  setPositions: (positions: ManualPosition[]) => void;
}

export const useManualTradingStore = create<ManualTradingState>((set) => ({
  connectionStatus: 'DISCONNECTED',
  lotSizes: {},
  positions: [],

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setLotSizes: (lotSizes) => set({ lotSizes }),
  setPositions: (positions) => set({ positions }),
}));
