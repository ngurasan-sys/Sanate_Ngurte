import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const norm = status.toUpperCase();

  const isBullish =
    norm.includes('BULLISH') ||
    norm.includes('BUY') ||
    norm.includes('SAFE') ||
    norm.includes('ACTIVE') ||
    norm.includes('COMPLETED') ||
    norm.includes('PASSED') ||
    norm.includes('LONG') ||
    norm.includes('CONNECTED');

  const isBearish =
    norm.includes('BEARISH') ||
    norm.includes('SELL') ||
    norm.includes('WARNING') ||
    norm.includes('LOSS') ||
    norm.includes('SHORT') ||
    norm.includes('REJECTED') ||
    norm.includes('FAILED') ||
    norm.includes('DISCONNECTED');

  const isBlocked =
    norm.includes('BLOCKED') ||
    norm.includes('SAFE HALT') ||
    norm.includes('INACTIVE');

  let styleClass = 'bg-zinc-800 text-zinc-300 border-zinc-700';

  if (isBullish) {
    styleClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  } else if (isBearish) {
    styleClass = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
  } else if (isBlocked) {
    styleClass = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  }

  return (
    <span
      className={`px-2 py-0.5 rounded text-[10px] font-semibold font-sans tracking-wider border uppercase select-none ${styleClass}`}
    >
      {status}
    </span>
  );
};

export default StatusBadge;
