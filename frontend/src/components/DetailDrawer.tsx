import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { mockDecisions } from '../mock/data';
import StatusBadge from './StatusBadge';

interface DetailDrawerProps {
  decisionId: string | null;
  onClose: () => void;
}

export const DetailDrawer: React.FC<DetailDrawerProps> = ({ decisionId, onClose }) => {
  if (!decisionId) return null;

  const decision = mockDecisions.find((d) => d.id === decisionId);
  if (!decision) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-zinc-900 border-l border-zinc-800 shadow-none flex flex-col h-full animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="h-16 px-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/80">
        <div className="flex items-center gap-2.5">
          <ShieldAlert size={16} className="text-emerald-400" />
          <span className="font-sans font-bold text-sm tracking-wider uppercase text-zinc-100">
            Decision intelligence deep dive
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-zinc-850 rounded-lg text-zinc-400 hover:text-zinc-200 transition-colors"
          aria-label="Close detail panel"
        >
          {/* Replaced X inline icon simply to compile cleanly */}
          <span className="text-[10px] font-mono font-bold tracking-wider">CLOSE</span>
        </button>
      </div>

      {/* Drawer content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Metric Header */}
        <div className="space-y-1">
          <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold font-sans">Instrument Setup</p>
          <h4 className="text-xl font-semibold font-sans text-zinc-100 uppercase">{decision.instrument}</h4>
          <div className="flex items-center gap-2 pt-1.5">
            <StatusBadge status={decision.risk} />
            <span className="text-[10px] font-mono text-zinc-400 tracking-wider">REGIME: {decision.regime}</span>
          </div>
        </div>

        {/* Quant scores */}
        <div className="pt-4 border-t border-zinc-850 space-y-4">
          <h5 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Coprocessor Signal Scores</h5>
          <div className="grid grid-cols-2 gap-4 font-mono text-xs">
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-850">
              <span className="text-zinc-500">Signal Score:</span>
              <p className="text-lg font-bold text-zinc-100 mt-1">{(decision.confidence * 1.15).toFixed(1)} / 100</p>
            </div>
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-850">
              <span className="text-zinc-500">Conflict Ratio:</span>
              <p className="text-lg font-bold text-rose-400 mt-1">{(decision.conflictScore * 0.8).toFixed(1)}%</p>
            </div>
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-850">
              <span className="text-zinc-500">Expected Value:</span>
              <p className="text-lg font-bold text-emerald-400 mt-1">+₹{decision.expectedValue}</p>
            </div>
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-850">
              <span className="text-zinc-500">Capital Leverage:</span>
              <p className="text-lg font-bold text-zinc-100 mt-1">1.2x max</p>
            </div>
          </div>
        </div>

        {/* Supporting criteria list */}
        <div className="pt-4 border-t border-zinc-850 space-y-3">
          <h5 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full inline-block" />
            Verified Supporting Criteria
          </h5>
          <ul className="space-y-2 text-xs text-zinc-300">
            {decision.supportingFactors.map((factor, idx) => (
              <li key={idx} className="bg-zinc-950/40 p-2.5 border border-zinc-850/60 rounded-md animate-none">
                {factor}
              </li>
            ))}
          </ul>
        </div>

        {/* Conflict factors list */}
        <div className="pt-4 border-t border-zinc-850 space-y-3">
          <h5 className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 bg-rose-400 rounded-full inline-block" />
            Elevated Conflict Factors
          </h5>
          <ul className="space-y-2 text-xs text-zinc-300">
            {decision.conflictingFactors.map((factor, idx) => (
              <li key={idx} className="bg-zinc-950/40 p-2.5 border border-zinc-850/60 rounded-md animate-none">
                {factor}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export default DetailDrawer;
