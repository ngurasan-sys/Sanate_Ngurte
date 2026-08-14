import React from 'react';
import { useTwoCandleStore } from '../../stores/twoCandleStore';
import { Check, X } from 'lucide-react';

const ConditionRow: React.FC<{
  title: string;
  description: string;
  isMet: boolean;
}> = ({ title, description, isMet }) => (
  <div className="flex items-start gap-4">
    <div className={`mt-0.5 flex-shrink-0 p-1 rounded-full ${isMet ? 'bg-emerald-500/10 text-emerald-500' : 'bg-zinc-800 text-zinc-500'}`}>
      {isMet ? <Check size={16} /> : <X size={16} />}
    </div>
    <div>
      <h4 className="text-zinc-100 font-sans font-medium text-sm">{title}</h4>
      <p className="text-zinc-400 font-sans text-xs mt-1">{description}</p>
    </div>
  </div>
);

export const TwoCandleDashboard: React.FC = () => {
  const { conditions, signalData } = useTwoCandleStore();

  const isPaused = signalData.status === 'PAUSED';
  const isSignalActive = signalData.status === 'SIGNAL_ACTIVE';

  // Banner Config
  const bannerBg = isPaused ? 'bg-slate-800/50' : isSignalActive ? 'bg-blue-900/20' : 'bg-blue-900/10';
  const bannerText = isPaused
    ? 'Strategy Paused: Outside 9:45 AM - 2:30 PM window.'
    : 'Monitoring 3-Minute Volume Anomalies...';
  const bannerTextColor = isPaused ? 'text-slate-300' : 'text-blue-400';

  return (
    <div className="w-full bg-[#0f172a] min-h-full p-8 flex flex-col gap-8">
      {/* Component 1: Strategy State Banner */}
      <div className={`w-full rounded-lg px-6 py-4 border border-zinc-800 flex items-center justify-center ${bannerBg}`}>
        <span className={`font-sans font-medium text-sm tracking-wide ${bannerTextColor}`}>
          {bannerText}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-grow">
        {/* Component 2: The Alignment Checklist (Left Panel) */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 space-y-6">
          <div className="border-b border-zinc-800 pb-4">
            <h3 className="text-zinc-100 font-sans font-bold text-lg tracking-wider uppercase">
              Alignment Checklist
            </h3>
            <p className="text-zinc-500 text-xs mt-1">Required conditions for signal trigger</p>
          </div>

          <div className="space-y-6">
            <ConditionRow
              title="Condition 1: Volume Spikes"
              description="Two consecutive 3-min candles > Threshold (50k/125k)."
              isMet={conditions.volumeSpike}
            />
            <ConditionRow
              title="Condition 2: Indicator Alignment"
              description="Price is definitively above/below VWAP, SuperTrend (10,2), and VWMA."
              isMet={conditions.indicatorAlignment}
            />
            <ConditionRow
              title="Condition 3: Momentum (RSI)"
              description="RSI (14) has room to run (Not >80 or <20)."
              isMet={conditions.momentumRoom}
            />
            <ConditionRow
              title="Condition 4: Trending OI"
              description="OI flow confirms the breakout direction."
              isMet={conditions.trendingOi}
            />
          </div>
        </div>

        {/* Component 3: Active Signal Action Card (Right Panel) */}
        <div className={`border rounded-xl p-8 transition-colors duration-300 flex flex-col justify-center ${
          isSignalActive
            ? 'bg-emerald-900/40 border-emerald-500'
            : 'bg-zinc-900 border-zinc-800'
        }`}>
          {isSignalActive ? (
            <div className="space-y-8">
              <div className="text-center">
                <h2 className="text-emerald-400 font-sans font-black text-4xl tracking-widest uppercase">
                  {signalData.signal.replace('_', ' ')}
                </h2>
                <p className="text-emerald-400/80 text-sm font-medium mt-2">Scalp Trade Setup</p>
              </div>

              <div className="bg-zinc-950/50 rounded-lg p-6 space-y-4 border border-emerald-500/20">
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400 font-sans text-sm">Suggested Entry:</span>
                  <span className="text-zinc-100 font-mono text-lg font-bold">
                    {signalData.currentPrice ? `₹${signalData.currentPrice}` : 'MKT'}
                  </span>
                </div>

                <div className="flex justify-between items-center border-t border-zinc-800 pt-4">
                  <span className="text-zinc-400 font-sans text-sm">Strict Stop-Loss:</span>
                  <span className="text-rose-500 font-mono text-xl font-bold bg-rose-500/10 px-3 py-1 rounded">
                    {signalData.stopLoss ? `₹${signalData.stopLoss.toFixed(2)}` : 'N/A'}
                  </span>
                </div>
              </div>

              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 text-center">
                <p className="text-emerald-300 font-sans text-sm font-medium">
                  Action Rule: Scalp trade. Trail stop-loss immediately upon entering profit.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-center h-full space-y-4">
              <div className="w-16 h-16 rounded-full bg-zinc-800/50 flex items-center justify-center mb-4">
                <div className="w-2 h-2 rounded-full bg-zinc-500 animate-ping" />
              </div>
              <h3 className="text-zinc-400 font-sans font-medium text-lg">Awaiting Setup</h3>
              <p className="text-zinc-600 font-sans text-sm max-w-xs">
                {signalData.reason}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
