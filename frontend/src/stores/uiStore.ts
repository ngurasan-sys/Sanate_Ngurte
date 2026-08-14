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
  | 'LEVELS'
  | 'TECHNICAL'
  | 'ORDER_FLOW'
  | 'QUANT'
  | 'STRATEGY_MONITOR'
  | 'GAP_OPENING_STRATEGIES'
  | 'LIVE_SIGNALS'
  | 'BACKTEST'
  | 'DECISION_INTEL'
  | 'POSITIONS'
  | 'ORDERS'
  | 'PNL'
  | 'RISK'
  | 'UPSTOX'
  | 'SYSTEM_HEALTH'
  | 'DATA_FEED';

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
