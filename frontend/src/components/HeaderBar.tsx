import React from 'react';
import { useMarketStore } from '../stores/marketStore';
import { useSystemStore } from '../stores/systemStore';
import { Wifi, Activity, Server } from 'lucide-react';

export const HeaderBar: React.FC = () => {
  const { indices } = useMarketStore();
  const { brokerageStatus, connectBroker, disconnectBroker } = useSystemStore();

  const nifty = indices.NIFTY;
  const sensex = indices.SENSEX;

  const handleBrokerToggle = () => {
    if (brokerageStatus.isConnected) {
      disconnectBroker();
    } else {
      connectBroker();
    }
  };

  return (
    <header className="h-14 border-b border-zinc-800 bg-zinc-900/60 backdrop-blur px-6 flex items-center justify-between text-xs text-zinc-400 select-none">
      {/* Index Tickers */}
      <div className="flex items-center gap-6">
        {/* NIFTY Ticker */}
        <div className="flex items-center gap-2">
          <span className="text-zinc-500 font-semibold tracking-wider">NIFTY</span>
          <span className="font-mono font-medium text-zinc-200 tabular-nums">
            {nifty.spot.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
          <span
            className={`font-mono text-[10px] tabular-nums ${
              nifty.change >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {nifty.change >= 0 ? '+' : ''}
            {nifty.change.toFixed(2)} ({nifty.changePercent >= 0 ? '+' : ''}
            {nifty.changePercent.toFixed(2)}%)
          </span>
        </div>

        <div className="w-[1px] h-3 bg-zinc-800" />

        {/* SENSEX Ticker */}
        <div className="flex items-center gap-2">
          <span className="text-zinc-500 font-semibold tracking-wider">SENSEX</span>
          <span className="font-mono font-medium text-zinc-200 tabular-nums">
            {sensex.spot.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
          <span
            className={`font-mono text-[10px] tabular-nums ${
              sensex.change >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {sensex.change >= 0 ? '+' : ''}
            {sensex.change.toFixed(2)} ({sensex.changePercent >= 0 ? '+' : ''}
            {sensex.changePercent.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* Connection & Latency Badges */}
      <div className="flex items-center gap-4">
        {/* Broker Connected */}
        <button
          onClick={handleBrokerToggle}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 transition-colors"
          title="Toggle broker connection simulation"
        >
          <Server size={12} className={brokerageStatus.isConnected ? 'text-emerald-400' : 'text-zinc-500'} />
          <span className="font-mono text-[10px] tracking-wider uppercase">
            {brokerageStatus.brokerName}: {brokerageStatus.isConnected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </button>

        {/* WS Connection & Latency */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-850 text-zinc-400">
          <Wifi
            size={12}
            className={
              brokerageStatus.wsStatus === 'CONNECTED'
                ? 'text-emerald-400 animate-pulse'
                : 'text-rose-400'
            }
          />
          <span className="font-mono text-[10px] tracking-wider uppercase">
            WS: {brokerageStatus.wsStatus === 'CONNECTED' ? `${brokerageStatus.wsLatency}ms` : 'OFFLINE'}
          </span>
        </div>

        {/* Market Status */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-850">
          <Activity
            size={12}
            className={
              brokerageStatus.marketStatus === 'MARKET OPEN' ? 'text-emerald-400' : 'text-rose-400'
            }
          />
          <span className="font-mono text-[10px] tracking-wider">
            {brokerageStatus.marketStatus}
          </span>
        </div>

        {/* Paper / Live Badge */}
        <span
          className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
            brokerageStatus.tradingStatus === 'LIVE'
              ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
              : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          }`}
        >
          {brokerageStatus.tradingStatus}
        </span>
      </div>
    </header>
  );
};

export default HeaderBar;
