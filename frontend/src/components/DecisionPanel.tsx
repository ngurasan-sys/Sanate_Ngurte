import React from 'react';
import { useDecisionStore } from '../stores/decisionStore';
import StatusBadge from './StatusBadge';
import { Sparkles, ArrowRight, CheckCircle2, AlertTriangle, HelpCircle } from 'lucide-react';

interface DecisionPanelProps {
  onOpenDrawer?: (decisionId: string) => void;
}

export const DecisionPanel: React.FC<DecisionPanelProps> = ({ onOpenDrawer }) => {
  const { decisions } = useDecisionStore();

  if (decisions.length === 0) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col items-center justify-center min-h-[300px]">
        <HelpCircle size={32} className="text-zinc-600 mb-2" />
        <h3 className="text-zinc-200 font-sans font-semibold text-sm uppercase">No Intelligence Signals</h3>
        <p className="text-xs text-zinc-500 mt-1 max-w-sm text-center">
          Decisions generate dynamically based on real-time multi-strike order flows and technical indicators.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
          Decision Intelligence & ML Coprocessor
        </h3>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Automated signal scores and confidence thresholds analysis</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {decisions.map((dec) => (
          <div
            key={dec.id}
            className="lg:col-span-3 bg-zinc-900 border border-zinc-800 rounded-lg p-6 lg:p-8 flex flex-col gap-6"
          >
            {/* Header section */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg border border-emerald-500/20">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h4 className="text-lg font-sans font-semibold text-zinc-100 uppercase tracking-wide">
                    {dec.instrument}
                  </h4>
                  <p className="text-[11px] font-mono text-zinc-500 tracking-wider">REGIME: {dec.regime}</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex flex-col items-end">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Risk Assessment</span>
                  <StatusBadge status={dec.risk} />
                </div>
              </div>
            </div>

            {/* Core Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Confidence</p>
                <p className="font-mono text-2xl font-semibold text-zinc-100 mt-1">{dec.confidence}%</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Expected Value (EV)</p>
                <p className="font-mono text-2xl font-semibold text-emerald-400 mt-1">+₹{dec.expectedValue}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Conflict Score</p>
                <p className="font-mono text-2xl font-semibold text-rose-400 mt-1">{dec.conflictScore}%</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Recommended action</p>
                <p className="font-mono text-sm font-semibold text-zinc-100 mt-2 uppercase">{dec.action}</p>
              </div>
            </div>

            {/* Supporting & Conflicting factors split */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2 border-t border-zinc-800/60">
              {/* Supporting */}
              <div className="space-y-3">
                <h5 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-1.5">
                  <CheckCircle2 size={13} className="text-emerald-400" />
                  Supporting Factors
                </h5>
                <ul className="space-y-2 text-xs">
                  {dec.supportingFactors.map((factor, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-zinc-300">
                      <ArrowRight size={12} className="text-emerald-500 shrink-0 mt-0.5" />
                      <span>{factor}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Conflicting */}
              <div className="space-y-3">
                <h5 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-1.5">
                  <AlertTriangle size={13} className="text-rose-400" />
                  Conflicting Factors
                </h5>
                <ul className="space-y-2 text-xs">
                  {dec.conflictingFactors.map((factor, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-zinc-300">
                      <ArrowRight size={12} className="text-rose-500 shrink-0 mt-0.5" />
                      <span>{factor}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Bottom Drawer trigger */}
            {onOpenDrawer && (
              <div className="flex justify-end pt-2 border-t border-zinc-800/40">
                <button
                  onClick={() => onOpenDrawer(dec.id)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 rounded-lg text-xs font-semibold tracking-wide transition-colors"
                >
                  View Decision Details
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DecisionPanel;
