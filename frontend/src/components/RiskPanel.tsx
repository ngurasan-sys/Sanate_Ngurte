import React from 'react';
import { useRiskStore } from '../stores/riskStore';
import MetricCard from './MetricCard';
import StatusBadge from './StatusBadge';

export const RiskPanel: React.FC = () => {
  const { riskSummary } = useRiskStore();

  if (!riskSummary) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
          <div>
            <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">Risk Management Control Center</h3>
            <p className="text-xs text-zinc-400 font-sans mt-0.5">Automated safety halts, leverage parameters, and drawdown guardrails</p>
          </div>
        </div>
        <div className="text-zinc-400 text-sm font-mono">NO DATA</div>
      </div>
    );
  }

  const metrics = [
    { label: 'Available Capital', value: `₹${(riskSummary.availableCapital || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` },
    { label: 'Available Margin', value: `₹${(riskSummary.availableMargin || 0).toLocaleString('en-IN')}` },
    { label: 'Margin Used', value: `₹${(riskSummary.marginUsed || 0).toLocaleString('en-IN')}` },
    { label: 'Today\'s Realized P&L', value: `${(riskSummary.dailyPnl || 0) >= 0 ? '+' : ''}₹${Math.abs(riskSummary.dailyPnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, subColor: (riskSummary.dailyPnl || 0) >= 0 ? ('bullish' as const) : ('bearish' as const) },
    { label: 'Daily Loss Limit', value: `₹${Math.abs(riskSummary.dailyLossLimit || 0).toLocaleString('en-IN')}`, subColor: 'bearish' as const },
    { label: 'Total Open Exposure', value: `₹${(riskSummary.exposure || 0).toLocaleString('en-IN')}` },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Risk Management Control Center
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">Automated safety halts, leverage parameters, and drawdown guardrails</p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500 font-bold uppercase tracking-wider">Composite Risk Status</span>
          <StatusBadge status={riskSummary.riskStatus || 'UNKNOWN'} />
        </div>
      </div>

      {/* Grid of cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {metrics.map((m, idx) => (
          <MetricCard
            key={idx}
            label={m.label}
            value={m.value}
            subValueColor={m.subColor || 'neutral'}
          />
        ))}
      </div>

      {/* Deep calculations area */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4 select-none">
        <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">
          Risk Parameter Calculations
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs text-zinc-400 font-mono">
          {riskSummary.detailedCalculations && (
            <>
              <div className="space-y-1">
                <span className="text-zinc-500 uppercase">Value-at-Risk (VaR)</span>
                <p className="text-zinc-200 font-bold text-sm">₹{riskSummary.detailedCalculations.varValue?.toLocaleString() || 'N/A'}</p>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-500 uppercase">Leverage Ratio</span>
                <p className="text-zinc-200 font-bold text-sm">{riskSummary.detailedCalculations.leverageRatio || 'N/A'}x Capital</p>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-500 uppercase">Stress Test Results</span>
                <p className="text-emerald-400 font-bold text-sm">{riskSummary.detailedCalculations.stressTestResult || 'N/A'}</p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default RiskPanel;
