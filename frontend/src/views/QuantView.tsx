import React from 'react';
import MetricCard from '../components/MetricCard';

const QuantView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Deterministic Quant Research</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time returns distribution, Z-scores and probability matrices.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <MetricCard label="Volatility Z-Score" value="1.14" subValue="Slightly above normal" subValueColor="neutral" />
        <MetricCard label="Expected Move Prob" value="68% within 24,620" subValue="Gaussian Distribution" subValueColor="neutral" />
        <MetricCard label="Signal Noise Ratio (SNR)" value="4.20" subValue="Clear breakout pattern" subValueColor="bullish" />
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4 font-mono text-xs text-zinc-400">
        <h4 className="font-sans font-bold text-zinc-100 uppercase tracking-wider">Model feature scoring metadata</h4>
        <div className="space-y-2">
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span>Chronological Split walk-forward validation:</span>
            <span className="text-emerald-400 font-semibold">PASSED</span>
          </div>
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span>Sharpe Ratio (Annualized):</span>
            <span className="text-zinc-200">2.42</span>
          </div>
          <div className="flex justify-between pb-1">
            <span>Sortino Ratio (Downside variance):</span>
            <span className="text-zinc-200">3.15</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default QuantView;
