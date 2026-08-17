import React, { memo } from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  subValue?: string | number;
  subValueColor?: 'bullish' | 'bearish' | 'neutral' | 'muted';
  /** Marks a card whose value is still hardcoded mock data, not live. */
  mock?: boolean;
}

/**
 * ⚡ Bolt Optimization: Wrapped in React.memo()
 * Impact: Prevents unnecessary re-renders of this heavily-used leaf component.
 * Used >15 times per page refresh, this ensures React skips diffing this component
 * unless its specific value props change.
 */
export const MetricCard: React.FC<MetricCardProps> = memo(({
  label,
  value,
  subValue,
  subValueColor = 'neutral',
  mock = false,
}) => {
  const getSubColorClass = () => {
    switch (subValueColor) {
      case 'bullish':
        return 'text-emerald-400';
      case 'bearish':
        return 'text-rose-400';
      case 'muted':
        return 'text-zinc-500';
      default:
        return 'text-zinc-400';
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col justify-between h-32 select-none">
      <span className="text-sm text-zinc-400 uppercase tracking-wider font-medium flex items-center gap-2">
        {label}
        {mock && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 tracking-normal">
            MOCK
          </span>
        )}
      </span>
      <div className="flex items-baseline justify-between mt-2">
        <span className="font-mono text-2xl font-semibold text-zinc-100 tabular-nums">
          {value}
        </span>
        {subValue !== undefined && (
          <span className={`font-mono text-xs tabular-nums ${getSubColorClass()}`}>
            {subValue}
          </span>
        )}
      </div>
    </div>
  );
});

export default MetricCard;
