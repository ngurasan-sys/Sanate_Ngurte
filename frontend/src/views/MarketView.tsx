import React from 'react';
import IndexDetailCard from '../components/IndexDetailCard';
import LevelPanel from '../components/LevelPanel';

interface MarketViewProps {
  symbol: 'NIFTY' | 'SENSEX';
}

const MarketView: React.FC<MarketViewProps> = ({ symbol }) => {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">{symbol} index levels & overview</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Comprehensive Spot and derivatives risk analytics</p>
      </div>
      <IndexDetailCard symbol={symbol} />
      <LevelPanel />
    </div>
  );
};

export default MarketView;
