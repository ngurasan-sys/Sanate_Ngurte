import React from 'react';
import { TwoCandleDashboard } from '../components/two_candle/TwoCandleDashboard';
import { useTwoCandleWebSocket } from '../hooks/useTwoCandleWebSocket';

export const TwoCandleView: React.FC = () => {
  useTwoCandleWebSocket('NIFTY');

  return (
    <div className="h-full w-full">
      <div className="mb-6">
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">
          2 Candle Breakout Scalper
        </h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">
          Real-time momentum breakouts based on volume anomalies and indicator confluences
        </p>
      </div>
      <TwoCandleDashboard />
    </div>
  );
};
