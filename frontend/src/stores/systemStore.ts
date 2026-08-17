import { create } from 'zustand';
import type { BrokerageStatus } from '../mock/interfaces';

interface SystemState {
  brokerageStatus: BrokerageStatus;
  setBrokerageStatus: (status: BrokerageStatus) => void;
  setWsStatus: (wsStatus: BrokerageStatus['wsStatus']) => void;
  setWsLatency: (wsLatency: number) => void;
  setTradingStatus: (tradingStatus: BrokerageStatus['tradingStatus']) => void;
  connectBroker: () => void;
  disconnectBroker: () => void;
}

const DEFAULT_BROKERAGE_STATUS: BrokerageStatus = {
  isConnected: false,
  wsStatus: 'DISCONNECTED',
  wsLatency: 0,
  brokerName: 'Upstox',
  marketStatus: 'MARKET CLOSED',
  account: {
    clientId: '',
    name: 'Upstox',
    authStatus: 'AUTHENTICATION REQUIRED',
  },
  tradingStatus: 'SAFE HALT',
};

export const useSystemStore = create<SystemState>((set) => ({
  brokerageStatus: DEFAULT_BROKERAGE_STATUS,
  setBrokerageStatus: (brokerageStatus) => set({ brokerageStatus }),
  setWsStatus: (wsStatus) =>
    set((state) => ({
      brokerageStatus: {
        ...state.brokerageStatus,
        wsStatus,
        isConnected: wsStatus === 'CONNECTED',
      },
    })),
  setWsLatency: (wsLatency) =>
    set((state) => ({
      brokerageStatus: {
        ...state.brokerageStatus,
        wsLatency,
      },
    })),
  setTradingStatus: (tradingStatus) =>
    set((state) => ({
      brokerageStatus: {
        ...state.brokerageStatus,
        tradingStatus,
      },
    })),
  connectBroker: () =>
    set((state) => ({
      brokerageStatus: {
        ...state.brokerageStatus,
        isConnected: true,
        wsStatus: 'CONNECTED',
        account: {
          ...state.brokerageStatus.account,
          authStatus: 'AUTHENTICATED',
        },
      },
    })),
  disconnectBroker: () =>
    set((state) => ({
      brokerageStatus: {
        ...state.brokerageStatus,
        isConnected: false,
        wsStatus: 'DISCONNECTED',
        account: {
          ...state.brokerageStatus.account,
          authStatus: 'AUTHENTICATION REQUIRED',
        },
      },
    })),
}));
export type { SystemState };
