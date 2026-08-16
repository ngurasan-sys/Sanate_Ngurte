import { create } from 'zustand';

export type NavigationPage =
  | 'DASHBOARD'
  | 'ALGO_DASHBOARD'
  | 'MARKET_NIFTY'
  | 'MARKET_SENSEX'
  | 'INTERACTIVE_CHART'
  | 'SPOT_OI'
  | 'FUTURE_OI'
  | 'OPTION_CHAIN'
  | 'GREEKS'
  | 'OPTION_ANALYTICS'
  | 'LEVELS'
  | 'TECHNICAL'
  | 'ORDER_FLOW'
  | 'QUANT'
  | 'STRATEGY_MONITOR'
  | 'GAP_OPENING_STRATEGIES'
  | 'THREE_MINUTE_GAP'
  | 'LIVE_SIGNALS'
  | 'BACKTEST'
  | 'PULLBACK_CHOP_FILTER'
  | 'DECISION_INTEL'
  | 'POSITIONS'
  | 'ORDERS'
  | 'PNL'
  | 'RISK'
  | 'UPSTOX'
  | 'SYSTEM_HEALTH'
  | 'DATA_FEED'
  | 'TRENDING_OI_PA'
  | 'TRENDING_OI_CROSSOVER'
  | 'STRADDLE'
  | 'INTRADAY_TREND_SCALPER'
  | 'MARKET_BREADTH'
  | 'TWO_CANDLE'
  | 'EXPIRY_REVERSAL'
  | 'EXPIRY_TRACKER'
  | 'EXECUTION_CONTROL'
  | 'BROKER_CONNECTIONS'
  | 'CAS_DISLOCATION'
  | 'OFAO';

interface UIState {
  sidebarExpanded: boolean;
  activePage: NavigationPage;
  expandedRows: Record<string, boolean>; // generic storage for table expands
  toggleSidebar: () => void;
  setSidebarExpanded: (expanded: boolean) => void;
  setActivePage: (page: NavigationPage) => void;
  toggleRowExpanded: (rowId: string) => void;
  clearExpandedRows: () => void;
}

export const useUiStore = create<UIState>((set) => ({
  sidebarExpanded: true,
  activePage: 'DASHBOARD',
  expandedRows: {},
  toggleSidebar: () => set((state) => ({ sidebarExpanded: !state.sidebarExpanded })),
  setSidebarExpanded: (sidebarExpanded) => set({ sidebarExpanded }),
  setActivePage: (activePage) => set({ activePage, expandedRows: {} }),
  toggleRowExpanded: (rowId) =>
    set((state) => ({
      expandedRows: {
        ...state.expandedRows,
        [rowId]: !state.expandedRows[rowId],
      },
    })),
  clearExpandedRows: () => set({ expandedRows: {} }),
}));
