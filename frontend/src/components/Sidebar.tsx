import React from 'react';
import { useUiStore } from '../stores/uiStore';
import type { NavigationPage } from '../stores/uiStore';
import {
  LayoutDashboard,
  TrendingUp,
  Flame,
  LineChart,
  GitBranch,
  ShieldAlert,
  ArrowUpDown,
  BookOpen,
  Settings,
  HelpCircle,
  FileText,
  Activity,
  Layers,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Link2,
  Crosshair
} from 'lucide-react';

interface SidebarItemProps {
  label: string;
  icon: React.ComponentType<{ className?: string; size?: number }>;
  page: NavigationPage;
}

export const Sidebar: React.FC = () => {
  const { sidebarExpanded, activePage, setActivePage, toggleSidebar } = useUiStore();

  const handlePageClick = (page: NavigationPage) => {
    setActivePage(page);
  };

  const menuItems: { section: string; items: SidebarItemProps[] }[] = [
    {
      section: 'CORE',
      items: [
        { label: 'DASHBOARD', icon: LayoutDashboard, page: 'DASHBOARD' },
        { label: 'ALGO DASHBOARD', icon: Activity, page: 'ALGO_DASHBOARD' },
      ],
    },
    {
      section: 'MARKET',
      items: [
        { label: 'NIFTY', icon: LineChart, page: 'MARKET_NIFTY' },
        { label: 'SENSEX', icon: LineChart, page: 'MARKET_SENSEX' },
        { label: 'Advanced Chart', icon: LineChart, page: 'INTERACTIVE_CHART' },
        { label: 'Market Breadth', icon: Activity, page: 'MARKET_BREADTH' },
      ],
    },
    {
      section: 'OPTIONS',
      items: [
        { label: 'Spot Trending OI', icon: Flame, page: 'SPOT_OI' },
        { label: 'Future Trending OI', icon: TrendingUp, page: 'FUTURE_OI' },
        { label: 'Option Chain', icon: Layers, page: 'OPTION_CHAIN' },
      ],
    },
    {
      section: 'ANALYSIS',
      items: [
        { label: 'Greeks', icon: Activity, page: 'GREEKS' },
        { label: 'Levels', icon: GitBranch, page: 'LEVELS' },
        { label: 'Technical', icon: Settings, page: 'TECHNICAL' },
        { label: 'Order Flow', icon: ArrowUpDown, page: 'ORDER_FLOW' },
        { label: 'Quant', icon: HelpCircle, page: 'QUANT' },
      ],
    },
    {
      section: 'STRATEGIES',
      items: [
        { label: 'Gap Opening Strategies', icon: BookOpen, page: 'GAP_OPENING_STRATEGIES' },
        { label: '3 Minute Gap', icon: BookOpen, page: 'THREE_MINUTE_GAP' },
        { label: 'Strategy Monitor', icon: BookOpen, page: 'STRATEGY_MONITOR' },
        { label: 'Live Signals', icon: Sparkles, page: 'LIVE_SIGNALS' },
        { label: 'Backtest', icon: FileText, page: 'BACKTEST' },
        { label: 'Trending OI + Price Action', icon: Flame, page: 'TRENDING_OI_PA' },
        { label: 'Straddle Monitor', icon: Activity, page: 'STRADDLE' },
        { label: 'Intraday Trend Scalper', icon: GitBranch, page: 'INTRADAY_TREND_SCALPER' },
        { label: 'Pullback Chop Filter', icon: Activity, page: 'PULLBACK_CHOP_FILTER' },
        { label: '2 Candle Scalper', icon: Crosshair, page: 'TWO_CANDLE' },
      ],
    },
    {
      section: 'DECISION',
      items: [
        { label: 'Decision Intel', icon: Sparkles, page: 'DECISION_INTEL' },
      ],
    },
    {
      section: 'TRADING',
      items: [
        { label: 'Positions', icon: Layers, page: 'POSITIONS' },
        { label: 'Orders', icon: FileText, page: 'ORDERS' },
        { label: 'P&L', icon: TrendingUp, page: 'PNL' },
        { label: 'Risk', icon: ShieldAlert, page: 'RISK' },
      ],
    },
    {
      section: 'BROKERAGE',
      items: [
        { label: 'Upstox', icon: Link2, page: 'UPSTOX' },
      ],
    },
    {
      section: 'SYSTEM',
      items: [
        { label: 'Health', icon: Activity, page: 'SYSTEM_HEALTH' },
        { label: 'Data Feed', icon: ArrowUpDown, page: 'DATA_FEED' },
      ],
    },
  ];

  return (
    <div className="flex flex-col h-screen text-zinc-400 select-none">
      {/* Brand Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-zinc-800">
        {sidebarExpanded ? (
          <span className="text-zinc-100 font-sans tracking-wider font-bold text-sm">ALGO_WORKSTATION</span>
        ) : (
          <span className="text-zinc-100 font-sans tracking-wider font-bold text-sm mx-auto">AW</span>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1 hover:bg-zinc-800 rounded transition-colors"
          aria-label="Toggle Sidebar"
        >
          {sidebarExpanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      {/* Menu Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
        {menuItems.map((group) => (
          <div key={group.section} className="space-y-1">
            {sidebarExpanded && (
              <div className="px-2 py-1 text-[10px] font-bold tracking-widest text-zinc-500">
                {group.section}
              </div>
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const isActive = activePage === item.page;
              return (
                <button
                  key={item.page}
                  onClick={() => handlePageClick(item.page)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150 ${
                    isActive
                      ? 'bg-zinc-800 text-zinc-100 font-medium'
                      : 'hover:bg-zinc-800/40 hover:text-zinc-300'
                  }`}
                  title={!sidebarExpanded ? item.label : undefined}
                >
                  <Icon className={`shrink-0 ${isActive ? 'text-zinc-100' : 'text-zinc-400'}`} size={16} />
                  {sidebarExpanded && <span className="truncate">{item.label}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Sidebar;
