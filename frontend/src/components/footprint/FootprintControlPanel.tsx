import React from 'react';
import type { Instrument, Timeframe } from '../../stores/useFootprintStore';

interface FootprintControlPanelProps {
  instrument: Instrument;
  timeframe: Timeframe;
  imbalanceRatioPct: number;
  connectionStatus: 'CONNECTED' | 'DISCONNECTED' | 'CONNECTING';
  onInstrumentChange: (instrument: Instrument) => void;
  onTimeframeChange: (timeframe: Timeframe) => void;
  onImbalanceRatioChange: (ratio: number) => void;
}

const INSTRUMENTS: Instrument[] = ['NIFTY FUT', 'BANKNIFTY FUT', 'SENSEX FUT'];
const TIMEFRAMES: Timeframe[] = ['1m', '3m', '5m', '15m'];

export const FootprintControlPanel: React.FC<FootprintControlPanelProps> = ({
  instrument, timeframe, imbalanceRatioPct, connectionStatus,
  onInstrumentChange, onTimeframeChange, onImbalanceRatioChange,
}) => {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <span className="text-xs text-zinc-500 uppercase tracking-wider font-bold">Ticker</span>
        <select
          className="bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 text-sm text-zinc-200 font-mono"
          value={instrument}
          onChange={(e) => onInstrumentChange(e.target.value as Instrument)}
        >
          {INSTRUMENTS.map((i) => <option key={i} value={i}>{i}</option>)}
        </select>
        <span
          className={`w-2 h-2 rounded-full ${connectionStatus === 'CONNECTED' ? 'bg-emerald-400' : 'bg-rose-400'}`}
          title={connectionStatus}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 uppercase tracking-wider font-bold mr-1">Timeframe</span>
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => onTimeframeChange(tf)}
            className={`px-3 py-1.5 rounded text-xs font-mono font-semibold transition-colors ${
              tf === timeframe ? 'bg-emerald-600 text-white' : 'bg-zinc-950 text-zinc-400 border border-zinc-800 hover:text-zinc-200'
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-1.5 min-w-[260px]">
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500 uppercase tracking-wider font-bold">Imbalance Ratio Dial</span>
          <span className="text-sm font-mono font-bold text-emerald-400">{imbalanceRatioPct}%</span>
        </div>
        <input
          type="range"
          min={200}
          max={500}
          step={10}
          value={imbalanceRatioPct}
          onChange={(e) => onImbalanceRatioChange(Number(e.target.value))}
          className="w-full accent-emerald-500"
        />
        <div className="flex justify-between text-[10px] text-zinc-600 font-mono">
          <span>200%</span>
          <span>500%</span>
        </div>
      </div>
    </div>
  );
};

export default FootprintControlPanel;
