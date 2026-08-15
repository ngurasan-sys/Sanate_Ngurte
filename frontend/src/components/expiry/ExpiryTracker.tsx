import React, { useEffect, useState } from 'react';

interface StrikeSide {
  ltp: number;
  oi_total: number;
  sentiment: string;
}

interface StrikeRow {
  strike_price: number;
  is_atm: boolean;
  call_data: StrikeSide;
  put_data: StrikeSide;
}

interface ExpiryTrackerState {
  sufficient_data: boolean;
  reason?: string;
  underlying_key?: string;
  spot_price?: number;
  atm_strike?: number;
  macro_clue?: string | null;
  strikes?: StrikeRow[];
}

const BULLISH_SENTIMENTS = new Set(['SHORT_COVERING', 'LONG_BUILDUP']);
const BEARISH_SENTIMENTS = new Set(['SHORT_BUILDUP', 'LONG_UNWINDING']);

const SentimentPill: React.FC<{ sentiment: string }> = ({ sentiment }) => {
  let classes = 'bg-[#182030] text-zinc-400 border-white/[0.05]';
  if (BULLISH_SENTIMENTS.has(sentiment)) {
    classes = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  } else if (BEARISH_SENTIMENTS.has(sentiment)) {
    classes = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
  }

  return (
    <span className={`inline-block px-2.5 py-1 rounded-full text-[10px] font-sans font-bold tracking-wider border ${classes}`}>
      {sentiment.replace(/_/g, ' ')}
    </span>
  );
};

const OiWeightBar: React.FC<{ callOi: number; putOi: number }> = ({ callOi, putOi }) => {
  const total = callOi + putOi;
  const callPct = total > 0 ? (callOi / total) * 100 : 50;

  return (
    <div className="h-1 w-full rounded-full overflow-hidden flex bg-[#182030]">
      <div className="h-full bg-emerald-500/60" style={{ width: `${callPct}%` }} />
      <div className="h-full bg-rose-500/60" style={{ width: `${100 - callPct}%` }} />
    </div>
  );
};

const StrikeCard: React.FC<{ row: StrikeRow }> = ({ row }) => {
  const ringClass = row.is_atm ? 'ring-1 ring-sky-500/50' : '';

  return (
    <div className={`bg-[#111622] rounded-xl p-5 mb-4 border border-white/[0.07] ${ringClass}`}>
      <div className="flex items-center">
        {/* Left 40%: Call Data */}
        <div className="flex-[2] flex flex-col gap-2">
          <span className="font-mono tabular-nums text-sm text-zinc-200">
            CE Prem: {row.call_data.ltp.toFixed(2)}
          </span>
          <span className="font-mono tabular-nums text-xs text-zinc-500">
            OI: {row.call_data.oi_total.toLocaleString('en-IN')}
          </span>
          <div>
            <SentimentPill sentiment={row.call_data.sentiment} />
          </div>
        </div>

        {/* Center 20%: Strike Price */}
        <div className="flex-1 flex flex-col items-center justify-center gap-1">
          {row.is_atm && (
            <span className="text-[10px] font-sans font-bold tracking-widest text-sky-400 uppercase">ATM</span>
          )}
          <span className="font-mono tabular-nums text-2xl font-bold text-zinc-100">
            {row.strike_price.toLocaleString('en-IN')}
          </span>
        </div>

        {/* Right 40%: Put Data */}
        <div className="flex-[2] flex flex-col items-end gap-2 text-right">
          <span className="font-mono tabular-nums text-sm text-zinc-200">
            PE Prem: {row.put_data.ltp.toFixed(2)}
          </span>
          <span className="font-mono tabular-nums text-xs text-zinc-500">
            OI: {row.put_data.oi_total.toLocaleString('en-IN')}
          </span>
          <div>
            <SentimentPill sentiment={row.put_data.sentiment} />
          </div>
        </div>
      </div>

      {/* OI Weight Bar */}
      <div className="mt-4">
        <OiWeightBar callOi={row.call_data.oi_total} putOi={row.put_data.oi_total} />
      </div>
    </div>
  );
};

const ScalpRulesWidget: React.FC = () => (
  <div className="bg-[#182030] border border-white/[0.05] rounded-xl p-6 space-y-5 sticky top-8">
    <h3 className="font-sans font-bold text-xs uppercase tracking-widest text-zinc-400">Expiry Scalp Rules</h3>
    <div className="space-y-4">
      <div>
        <p className="font-sans font-bold text-sm text-zinc-200">Rule 1: Scalp Only</p>
        <p className="font-sans text-xs text-zinc-500 mt-1">Exit within minutes of profit.</p>
      </div>
      <div>
        <p className="font-sans font-bold text-sm text-zinc-200">Rule 2: Respect the Trend</p>
        <p className="font-sans text-xs text-zinc-500 mt-1">Do not fight the 50% OI difference trend.</p>
      </div>
      <div>
        <p className="font-sans font-bold text-sm text-zinc-200">Rule 3: Time Cutoff</p>
        <p className="font-sans text-xs text-zinc-500 mt-1">Avoid new entries after 2:30 PM (Theta Decay risk).</p>
      </div>
    </div>
  </div>
);

export const ExpiryTracker: React.FC = () => {
  const [state, setState] = useState<ExpiryTrackerState | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/ws/expiry_tracker');

      ws.onmessage = (event) => {
        try {
          setState(JSON.parse(event.data));
        } catch (e) {
          console.error('Failed to parse expiry_tracker message', e);
        }
      };

      ws.onclose = () => {
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  const noData = !state || !state.sufficient_data;

  return (
    <div className="min-h-screen bg-[#0B0E14] text-zinc-100 p-8 select-none">
      <div className="mb-8">
        <h2 className="font-sans font-bold text-lg uppercase tracking-wider text-zinc-100">OI Expiry Tracker</h2>
        <p className="font-sans text-xs text-zinc-500 mt-1">
          Real-time trap detection and Option Chain sentiment for expiry day scalping.
        </p>
      </div>

      {/* Top Macro Ribbon */}
      <div className="w-full bg-sky-900/20 text-sky-400 border border-sky-800/30 rounded-xl p-6 mb-8">
        <p className="font-sans text-sm">
          {state?.macro_clue ?? (noData ? (state?.reason ?? 'Connecting…') : 'No macro clue detected right now.')}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-8">
        {/* Strike Zone */}
        <div>
          {noData ? (
            <div className="bg-[#111622] border border-white/[0.07] rounded-xl p-8 flex items-center justify-center text-center">
              <p className="text-zinc-500 font-sans text-sm">{state?.reason ?? 'Waiting for option chain data…'}</p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4 px-1">
                <span className="font-mono tabular-nums text-xs text-zinc-500">
                  Spot: {state?.spot_price?.toLocaleString('en-IN')}
                </span>
                <span className="font-mono tabular-nums text-xs text-zinc-500">
                  ATM: {state?.atm_strike?.toLocaleString('en-IN')}
                </span>
              </div>
              {state?.strikes?.map((row) => (
                <StrikeCard key={row.strike_price} row={row} />
              ))}
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div>
          <ScalpRulesWidget />
        </div>
      </div>
    </div>
  );
};

export default ExpiryTracker;
