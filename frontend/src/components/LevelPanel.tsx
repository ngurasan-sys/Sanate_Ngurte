import React from 'react';
import { useLiveLevels } from '../hooks/useLiveLevels';

interface LevelPanelProps {
  instrument: string;
}

export const LevelPanel: React.FC<LevelPanelProps> = ({ instrument }) => {
  const { levels, loading, error, refetch } = useLiveLevels(instrument);

  const resistance = levels.filter((l) => l.levelType === 'Resistance').sort((a, b) => a.price - b.price);
  const support = levels.filter((l) => l.levelType === 'Support').sort((a, b) => b.price - a.price);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Market Levels
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time swing-based support/resistance — {instrument}</p>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-sans bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {!error && levels.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No levels detected yet — needs enough closed candles from a live feed.
        </div>
      )}

      {levels.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <div>
            <h4 className="text-rose-400 font-sans text-xs font-bold uppercase tracking-wider mb-2">Resistance</h4>
            <div className="space-y-2 font-mono text-sm">
              {resistance.map((l) => (
                <div key={l.levelId} className="flex justify-between border-b border-zinc-800/60 pb-2">
                  <span className="text-zinc-400">{l.timeframe}</span>
                  <span className="text-zinc-100 font-semibold">{l.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-emerald-400 font-sans text-xs font-bold uppercase tracking-wider mb-2">Support</h4>
            <div className="space-y-2 font-mono text-sm">
              {support.map((l) => (
                <div key={l.levelId} className="flex justify-between border-b border-zinc-800/60 pb-2">
                  <span className="text-zinc-400">{l.timeframe}</span>
                  <span className="text-zinc-100 font-semibold">{l.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LevelPanel;
