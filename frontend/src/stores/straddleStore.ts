import { create } from 'zustand';

export interface StraddleData {
  current_premium: number;
  vwap: number;
  ema_20: number;
  action: string;
  trailing_sl: number;
}

export interface StraddleState {
  timestamp: string;
  underlying: number;
  atm_strike: number;
  market_regime: string;
  straddle_data: StraddleData;
}

interface StraddleStore {
  isConnected: boolean;
  state: StraddleState | null;
  history: Array<{ time: string; premium: number; vwap: number; ema_20: number }>;
  connect: () => void;
  disconnect: () => void;
}

let ws: WebSocket | null = null;

export const useStraddleStore = create<StraddleStore>((set, get) => ({
  isConnected: false,
  state: null,
  history: [],

  connect: () => {
    if (ws) return;

    ws = new WebSocket('ws://localhost:8000/ws/straddle');

    ws.onopen = () => {
      set({ isConnected: true });
    };

    ws.onmessage = (event) => {
      try {
        const data: StraddleState = JSON.parse(event.data);
        const currentHistory = get().history;

        // Append to history for chart
        const newEntry = {
          time: data.timestamp,
          premium: data.straddle_data.current_premium,
          vwap: data.straddle_data.vwap,
          ema_20: data.straddle_data.ema_20,
        };

        const updatedHistory = [...currentHistory, newEntry];

        // Keep max 1000 points in history to prevent memory leaks
        if (updatedHistory.length > 1000) {
          updatedHistory.shift();
        }

        set({
          state: data,
          history: updatedHistory,
        });
      } catch (error) {
        console.error('Failed to parse straddle data:', error);
      }
    };

    ws.onclose = () => {
      set({ isConnected: false });
      ws = null;
      // Auto reconnect
      setTimeout(() => get().connect(), 5000);
    };

    ws.onerror = (error) => {
      console.error('Straddle WebSocket error:', error);
    };
  },

  disconnect: () => {
    if (ws) {
      ws.close();
      ws = null;
      set({ isConnected: false });
    }
  },
}));
