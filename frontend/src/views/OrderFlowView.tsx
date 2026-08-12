import React from 'react';
import MetricCard from '../components/MetricCard';

const OrderFlowView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Real-time Order Flow Analytics</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Aggressive buying blocks and cumulative volume delta (CVD) tracking.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <MetricCard label="Cumulative Volume Delta" value="+1,45,000" subValue="Aggressive buying surge" subValueColor="bullish" />
        <MetricCard label="Bid/Ask Imbalance" value="3.4x Buying" subValue="High institutional demand" subValueColor="bullish" />
        <MetricCard label="Consolidated Spread" value="0.05" subValue="Ultra-liquid optimal entry" subValueColor="neutral" />
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 font-sans text-xs text-zinc-400 space-y-4">
        <h4 className="font-bold text-zinc-100 uppercase tracking-wider">Subtle order flow imbalance logs</h4>
        <div className="space-y-2 font-mono">
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span className="text-zinc-500">14:29:58 - Imbalance CE Strike 24500:</span>
            <span className="text-emerald-400">BUY Block 85,000 qty @ 112.10</span>
          </div>
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span className="text-zinc-500">14:29:12 - Spread execution:</span>
            <span className="text-zinc-300">Smart route routing via Upstox optimal book match</span>
          </div>
          <div className="flex justify-between pb-1">
            <span className="text-zinc-500">14:28:44 - Imbalance PE Strike 24400:</span>
            <span className="text-rose-400">SELL Block 45,000 qty @ 78.45</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OrderFlowView;
