import React from 'react';
import StatusBadge from '../components/StatusBadge';
import { Activity } from 'lucide-react';

const LiveSignalsView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Real-time Signals Audit Stream</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Live trigger logs with complete confidence tracking and entry buffer criteria.</p>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-emerald-400" />
          <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">Intraday Strategy Triggers</h4>
        </div>

        <div className="space-y-3 font-mono text-xs text-zinc-300">
          {[
            { time: '14:21:05', strategy: '15-Min Breakout', action: 'BUY CE', status: 'FILLED', conf: '78%' },
            { time: '14:02:11', strategy: 'Mean Reversion (Bollinger)', action: 'BUY PE', status: 'FILLED', conf: '42%' },
            { time: '13:30:00', strategy: 'Order Flow Scalper', action: 'HOLD', status: 'TRIGGERED', conf: '55%' },
          ].map((sig, idx) => (
            <div key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
              <div className="flex items-center gap-3">
                <span className="text-zinc-500">{sig.time}</span>
                <span className="font-bold text-zinc-100">{sig.strategy}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-emerald-400 font-semibold">{sig.action}</span>
                <span className="text-zinc-400">Confidence: {sig.conf}</span>
                <StatusBadge status={sig.status} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default LiveSignalsView;
