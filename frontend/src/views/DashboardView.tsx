import React from 'react';
import MetricCard from '../components/MetricCard';
import DecisionPanel from '../components/DecisionPanel';
import IndexDetailCard from '../components/IndexDetailCard';
import { usePortfolioStore } from '../stores/portfolioStore';

interface DashboardViewProps {
  onOpenDecisionDrawer: (id: string) => void;
}

const DashboardView: React.FC<DashboardViewProps> = ({ onOpenDecisionDrawer }) => {
  const { totalPnl, todayPnl, positions } = usePortfolioStore();

  return (
    <div className="space-y-8 select-none">
      {/* Header / Intro */}
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Trading Workstation Dashboard</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Minimalist, spacious overview of systems, strategies, decision score and risk controls.</p>
      </div>

      {/* Top Index Tickers Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <IndexDetailCard symbol="NIFTY" />
        <IndexDetailCard symbol="SENSEX" />
      </div>

      {/* Portfolio Summary */}
      <div className="space-y-4">
        <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Portfolio & Margin Summary</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard
            label="Total Realized P&L"
            value={`${totalPnl >= 0 ? '+' : ''}₹${totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            subValueColor={totalPnl >= 0 ? 'bullish' : 'bearish'}
            subValue="All-time compiled"
          />
          <MetricCard
            label="Today's P&L"
            value={`${todayPnl >= 0 ? '+' : ''}₹${todayPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            subValueColor={todayPnl >= 0 ? 'bullish' : 'bearish'}
            subValue="Live MTM ticks"
          />
          <MetricCard
            label="Active Positions"
            value={positions.filter(p => p.status === 'ACTIVE').length}
            subValue="Working on market"
          />
          <MetricCard
            label="Available Margin"
            value="₹4,82,500"
            subValue="Margin used: ₹1,24,500"
          />
        </div>
      </div>

      {/* Strategic Overview Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column: Decision Intel */}
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Executive Decision Intelligence</h3>
          <DecisionPanel onOpenDrawer={onOpenDecisionDrawer} />
        </div>

        {/* Right Column: Strategy overview */}
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Top Performing Strategy</h3>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm text-zinc-200">15-Min Breakout</span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans font-bold">
                ACTIVE
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-xs font-mono">
              <div>
                <span className="text-zinc-500">Live Signal:</span>
                <p className="text-zinc-100 font-bold mt-0.5">BUY CE</p>
              </div>
              <div>
                <span className="text-zinc-500">Confidence Score:</span>
                <p className="text-emerald-400 font-bold mt-0.5">78%</p>
              </div>
              <div>
                <span className="text-zinc-500">Parameters:</span>
                <p className="text-zinc-400 mt-0.5">Strike: ATM | TF: 15m</p>
              </div>
              <div>
                <span className="text-zinc-500">Historical win-rate:</span>
                <p className="text-zinc-100 font-bold mt-0.5">64.5% (124 trades)</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardView;
