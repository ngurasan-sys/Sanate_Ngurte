import React from 'react';
import MetricCard from '../components/MetricCard';

const BacktestView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Quantitative Historical Backtest reports</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Robust parameter optimization preventing future look-ahead and overlap contamination.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <MetricCard label="CAGR %" value="42.5%" />
        <MetricCard label="Profit Factor" value="1.84" />
        <MetricCard label="Max Drawdown" value="-8.42%" subValueColor="bearish" />
        <MetricCard label="Sharpe Ratio" value="2.45" />
      </div>

      {/* Backtest table summary */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">Strategy Backtest runs</h4>
        <div className="space-y-3 text-xs font-mono text-zinc-400">
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span className="font-sans text-zinc-300 font-bold">15-Min Range breakout model:</span>
            <span className="text-emerald-400 font-semibold">PASSED (CAGR: 45.1%, Sharpe: 2.6)</span>
          </div>
          <div className="flex justify-between border-b border-zinc-850 pb-2">
            <span className="font-sans text-zinc-300 font-bold">Bollinger Bands Mean Reversion:</span>
            <span className="text-zinc-300">PASSED (CAGR: 28.2%, Sharpe: 1.8)</span>
          </div>
          <div className="flex justify-between pb-1">
            <span>Slippage and latency assumptions model:</span>
            <span className="text-zinc-500">1.2ms avg network delay calculated</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BacktestView;
