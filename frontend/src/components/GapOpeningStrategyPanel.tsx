import React from 'react';
import MetricCard from './MetricCard';
import StatusBadge from './StatusBadge';
import { useMarketStore } from '../stores/marketStore';

const GapOpeningStrategyPanel: React.FC = () => {
  const { indices } = useMarketStore();
  const nifty = indices['NIFTY'];

  // Default values mapping
  const previousClose = 24450.0;
  const todayOpen = nifty?.spot || 24500.0;
  const gapPoints = todayOpen - previousClose;
  const gapPercent = (gapPoints / previousClose) * 100;

  let gapDirection = 'FLAT';
  if (gapPercent > 0.1) gapDirection = 'GAP UP';
  else if (gapPercent < -0.1) gapDirection = 'GAP DOWN';

  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Gap Opening Strategies</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Automated trading model based on initial balance gap discovery</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
        <MetricCard label="Previous Close" value={`₹${previousClose.toFixed(2)}`} />
        <MetricCard label="Today's Open" value={`₹${todayOpen.toFixed(2)}`} />
        <MetricCard label="Gap Points" value={gapPoints.toFixed(2)} subValueColor={gapPoints >= 0 ? 'bullish' : 'bearish'} />
        <MetricCard label="Gap %" value={`${gapPercent.toFixed(2)}%`} subValueColor={gapPercent >= 0 ? 'bullish' : 'bearish'} />
        <MetricCard label="Gap Direction" value={gapDirection} subValueColor={gapDirection === 'GAP UP' ? 'bullish' : gapDirection === 'GAP DOWN' ? 'bearish' : 'neutral'} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Strategy Status</h4>
            <div className="space-y-2 font-mono text-xs text-zinc-400">
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Strategy:</span>
                    <span className="text-zinc-100 font-bold">Gap Opening Strategies</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Market Phase:</span>
                    <StatusBadge status="OPENING DISCOVERY" />
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Opening Time:</span>
                    <span>09:15 IST</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Entry Evaluation From:</span>
                    <span>09:45 IST</span>
                </div>
                <div className="flex justify-between pb-1">
                    <span>Execution Mode:</span>
                    <span className="text-amber-400 font-bold border border-amber-500/20 px-1 py-0.5 rounded">DATA_ONLY</span>
                </div>
            </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Market Intelligence</h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs text-zinc-400">
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Trending OI:</span>
                    <span className="text-emerald-400">BULLISH</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Diff OI:</span>
                    <span>+1,250,000</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Diff OI %:</span>
                    <span className="text-emerald-400">+42.5%</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Net PCR:</span>
                    <span>1.15</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>VWAP:</span>
                    <span>24485.50</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>SuperTrend:</span>
                    <span>24460.00</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Daily ATR(14):</span>
                    <span>185.50</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Day Range:</span>
                    <span>95.00</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>ATR Usage:</span>
                    <span>51.2%</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>ATR Exhaustion:</span>
                    <StatusBadge status="SAFE" />
                </div>
            </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Entry Logic & Status</h4>
            <div className="space-y-2 font-mono text-xs text-zinc-400">
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Tier 1:</span>
                    <StatusBadge status="WAITING" />
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-2">
                    <span>Tier 2:</span>
                    <StatusBadge status="WAITING" />
                </div>
            </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Position Management</h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs text-zinc-400">
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Entry Price:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Current Price:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Current Stop:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Unrealized P&L:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Position State:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Partial Profit Status:</span>
                    <span>--</span>
                </div>
                <div className="flex justify-between border-b border-zinc-850 pb-1">
                    <span>Trailing Status:</span>
                    <span>--</span>
                </div>
            </div>
        </div>
      </div>

    </div>
  );
};

export default GapOpeningStrategyPanel;
