import { create } from 'zustand';

export interface FootprintNode {
  price: number;
  bid_volume: number;
  ask_volume: number;
  delta: number;
  total_volume: number;
}

export interface FootprintCandle {
  instrument_key: string;
  timeframe: string;
  open_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  is_closed: boolean;
  footprint: Record<string, FootprintNode>;
  buy_volume: number;
  sell_volume: number;
  delta: number;
  poc_price: number | null;
}

export type Instrument = 'NIFTY FUT' | 'BANKNIFTY FUT' | 'SENSEX FUT';
export type Timeframe = '1m' | '3m' | '5m' | '15m';

interface FootprintState {
  instrument: Instrument;
  timeframe: Timeframe;
  imbalanceRatioPct: number; // 200-500, purely client-side — see FootprintChart's imbalance math
  currentCandle: FootprintCandle | null;
  history: FootprintCandle[];
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';

  setInstrument: (instrument: Instrument) => void;
  setTimeframe: (timeframe: Timeframe) => void;
  setImbalanceRatioPct: (ratio: number) => void;
  applyCandleUpdate: (instrumentKey: string, candlesByTimeframe: Record<string, FootprintCandle>) => void;
  setConnectionStatus: (status: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING') => void;
}

export const useFootprintStore = create<FootprintState>((set, get) => ({
  instrument: 'NIFTY FUT',
  timeframe: '5m',
  imbalanceRatioPct: 300,
  currentCandle: null,
  history: [],
  connectionStatus: 'DISCONNECTED',

  setInstrument: (instrument) => set({ instrument, currentCandle: null, history: [] }),
  setTimeframe: (timeframe) => set({ timeframe, currentCandle: null, history: [] }),
  setImbalanceRatioPct: (ratio) => set({ imbalanceRatioPct: ratio }),

  applyCandleUpdate: (instrumentKey, candlesByTimeframe) => {
    const { instrument, timeframe, currentCandle, history } = get();
    if (instrumentKey !== instrument) return;

    const candle = candlesByTimeframe[timeframe];
    if (!candle) return;

    // A new open_time means the previous "current" candle just closed —
    // archive it into history instead of discarding it.
    if (currentCandle && currentCandle.open_time !== candle.open_time) {
      const nextHistory = [...history, { ...currentCandle, is_closed: true }].slice(-100);
      set({ currentCandle: candle, history: nextHistory });
    } else {
      set({ currentCandle: candle });
    }
  },

  setConnectionStatus: (status) => set({ connectionStatus: status }),
}));
