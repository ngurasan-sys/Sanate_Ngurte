import React from 'react';
import { Activity } from 'lucide-react';
import { useMarketStore } from '../stores/marketStore';
import { mockOptionChains } from '../mock/data';

const DataFeedView: React.FC = () => {
  const { indices } = useMarketStore();
  const nifty = indices.NIFTY;
  const sensex = indices.SENSEX;
  const niftyChains = mockOptionChains['NIFTY'];
  const activeChain = niftyChains && niftyChains[0];

  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">WebSockets Live Normalizer Feed</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Incremental feed status with zero layout jitter.</p>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-sky-400" />
          <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Normalization Streams logs</h4>
        </div>
        <div className="space-y-2 font-mono text-xs text-zinc-400">
          <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
            <span className="text-zinc-500">14:29:58 -</span> Normalizer mapped tick: NIFTY Spot: <span className="text-zinc-100">{nifty.spot.toFixed(2)}</span>, Change: <span className={nifty.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{nifty.change.toFixed(2)}</span>
          </div>
          <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
            <span className="text-zinc-500">14:29:58 -</span> Normalizer mapped tick: SENSEX Spot: <span className="text-zinc-100">{sensex.spot.toFixed(2)}</span>, Change: <span className={sensex.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{sensex.change.toFixed(2)}</span>
          </div>
          <div className="p-3 bg-zinc-950/40 border border-zinc-850 rounded-lg">
            <span className="text-zinc-500">14:29:58 -</span> Option normalizer snapshot: CE strike 24500 ltp updated to <span className="text-emerald-400">₹{activeChain?.strikes.find((s) => s.strike === 24500)?.ce.ltp}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataFeedView;
