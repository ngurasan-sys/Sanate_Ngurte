import React from 'react';
import MetricCard from './MetricCard';
import ChartPanel from './ChartPanel';

export const GreeksPanel: React.FC = () => {
  const greeks = [
    { label: 'ATM Call Delta', value: '0.52', subValue: 'Bullish Bias', color: 'bullish' as const },
    { label: 'Portfolio Net Gamma', value: '0.0007', subValue: 'Long Volatility', color: 'bullish' as const },
    { label: 'Portfolio Net Theta', value: '-₹2,450.00', subValue: 'Daily Decay', color: 'bearish' as const },
    { label: 'Portfolio Net Vega', value: '₹4,120.00', subValue: 'IV Expansion profit', color: 'bullish' as const },
  ];

  // IV curve chart mock data
  const ivData = [
    { time: '2026-08-11', value: 14.10 },
    { time: '2026-08-12', value: 14.20 },
    { time: '2026-08-13', value: 14.15 },
    { time: '2026-08-14', value: 14.30 },
    { time: '2026-08-15', value: 14.50 },
    { time: '2026-08-16', value: 14.40 },
    { time: '2026-08-17', value: 14.20 },
  ];

  return (
    <div className="space-y-6 select-none">
      <div>
        <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
          Portfolio Greeks & Volatility exposure
        </h3>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real-time composite option greeks aggregation</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {greeks.map((g, idx) => (
          <MetricCard
            key={idx}
            label={g.label}
            value={g.value}
            subValue={g.subValue}
            subValueColor={g.color}
          />
        ))}
      </div>

      <ChartPanel title="Implied Volatility (IV) Trend Chart" data={ivData} />
    </div>
  );
};

export default GreeksPanel;
