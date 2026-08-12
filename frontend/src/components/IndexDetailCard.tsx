import React from 'react';
import StatusBadge from './StatusBadge';
import { useMarketStore } from '../stores/marketStore';

interface IndexDetailCardProps {
  symbol: 'NIFTY' | 'SENSEX';
}

const IndexDetailCard: React.FC<IndexDetailCardProps> = ({ symbol }) => {
  const { indices } = useMarketStore();
  const data = indices[symbol];

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <span className="font-sans font-bold text-sm tracking-wider uppercase text-zinc-100">{symbol} Summary</span>
        <StatusBadge status={data.trend} />
      </div>
      <div className="grid grid-cols-2 gap-4 font-mono text-xs text-zinc-400">
        <div>
          <span className="text-zinc-500 block">Spot:</span>
          <span className="text-sm font-semibold text-zinc-100">₹{data.spot.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-zinc-500 block">VWAP:</span>
          <span className="text-sm font-semibold text-zinc-100">₹{data.vwap.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-zinc-500 block">Support:</span>
          <span className="text-sm font-semibold text-emerald-400">₹{data.support.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-zinc-500 block">Resistance:</span>
          <span className="text-sm font-semibold text-rose-400">₹{data.resistance.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-zinc-500 block">IV %:</span>
          <span className="text-sm font-semibold text-zinc-100">{data.iv}%</span>
        </div>
        <div>
          <span className="text-zinc-500 block">Expected Move:</span>
          <span className="text-sm font-semibold text-zinc-100">±{data.expectedMove}</span>
        </div>
      </div>
    </div>
  );
};

export default IndexDetailCard;
