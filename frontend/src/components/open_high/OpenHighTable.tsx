import React from 'react';

// No production data source: the backend's oh_ol_strategy engine only
// exposes a per-instrument live-stream adapter (adapt_oh_ol in
// live_stream_adapters.py), not a list/table endpoint this multi-row
// table could consume. Rather than force-fit a mismatched integration,
// this shows NO DATA honestly until a real list endpoint exists.
interface OHSignal {
  id: string;
  instrument: string;
  probability: number;
  time: string;
  dailyRange: number;
  atr: number;
  isActive: boolean;
  entryPrice?: number;
  stopLoss?: number;
  status?: string;
}

const signals: OHSignal[] = [];

export const OpenHighTable: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Open=High (O=H) Strategy</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Strict probability filters and dynamic execution</p>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        {signals.length === 0 && (
          <div className="text-zinc-500 font-mono text-xs py-6 text-center">NO DATA</div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left whitespace-nowrap">
            <thead className="text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="pb-2 font-normal uppercase">Time</th>
                <th className="pb-2 font-normal uppercase">Instrument</th>
                <th className="pb-2 font-normal uppercase">Probability</th>
                <th className="pb-2 font-normal uppercase">ATR Status</th>
                <th className="pb-2 font-normal uppercase">Execution State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-850 text-zinc-300">
              {signals.map((sig) => {
                const atrExhaustionNear = sig.dailyRange >= (sig.atr * 0.95);

                return (
                  <tr key={sig.id} className="hover:bg-zinc-800/30">
                    <td className="py-4 text-zinc-500">{sig.time}</td>
                    <td className="py-4 font-bold text-zinc-100">{sig.instrument}</td>

                    {/* Probability Column with Red Dot indicator for >= 90% */}
                    <td className="py-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono tabular-nums">{sig.probability}%</span>
                        {sig.probability >= 90 && (
                          <div className="flex items-center gap-1 text-rose-400">
                            <div className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                            <span className="text-[10px] uppercase font-bold tracking-wider">High Conviction</span>
                          </div>
                        )}
                      </div>
                    </td>

                    {/* ATR Status Banner */}
                    <td className="py-4">
                      <div className={`inline-flex items-center px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider border ${
                        atrExhaustionNear
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                      }`}>
                        Daily Range: {sig.dailyRange} / ATR: {sig.atr}
                      </div>
                    </td>

                    {/* Active Signal / Execution Card */}
                    <td className="py-4">
                      {sig.isActive ? (
                        <div className="flex flex-col gap-1 border border-zinc-800 rounded bg-zinc-950 p-2 text-[10px]">
                          <div className="flex justify-between">
                            <span className="text-zinc-500 uppercase">Avg Entry:</span>
                            <span className="font-mono tabular-nums text-zinc-300">₹{sig.entryPrice?.toFixed(2)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-zinc-500 uppercase">Active Stop-Loss:</span>
                            <span className="font-mono tabular-nums text-rose-400 font-bold">₹{sig.stopLoss?.toFixed(2)}</span>
                          </div>
                          <div className="mt-1 pt-1 border-t border-zinc-800 text-sky-400 uppercase tracking-wider font-bold">
                            {sig.status}
                          </div>
                        </div>
                      ) : (
                        <span className="text-zinc-600 uppercase text-[10px] tracking-wider">Not Active</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default OpenHighTable;
