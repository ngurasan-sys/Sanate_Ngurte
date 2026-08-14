import React, { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Clock } from 'lucide-react';

interface BtstCasState {
  status: string;
  message: string;
  signal: string;
  deadline?: string;
  pillar_macro: boolean;
  pillar_micro: boolean;
  pillar_cas: boolean;
  futures_trend: string;
  post_1pm_oi: {
    call_oi_change: number;
    put_oi_change: number;
  };
  cas_market_state: {
    equilibrium_price: number;
    day_high: number;
    day_low: number;
  };
  current_time_str: string;
}

export const BtstDashboardView: React.FC = () => {
  const [data, setData] = useState<BtstCasState | null>(null);
  const [, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/ws/btst_cas');

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setData(parsed);
        } catch (e) {
          console.error("Error parsing BTST CAS data", e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        // Reconnect after 3 seconds
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (err) => {
        console.error('BTST CAS WebSocket Error:', err);
        ws.close();
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.close();
      }
    };
  }, []);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-400 font-sans p-6">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
          <p>Connecting to BTST CAS Engine...</p>
        </div>
      </div>
    );
  }

  // Parse time manually from the mock "HH:MM:SS" since datetime objects in JS are annoying with just times
  const timeStr = data.current_time_str;
  const isCasWindow = timeStr >= "15:15:00" && timeStr < "15:35:00";
  const isGoldenWindow = timeStr >= "15:35:00" && timeStr < "15:40:00";

  let bannerClass = "bg-slate-900 border-slate-800 text-slate-300";
  let bannerText = `Market Open: Gathering Post-1 PM OI Data. (Current Time: ${timeStr})`;

  if (isCasWindow) {
    bannerClass = "bg-amber-950/40 border-amber-800 text-amber-200";
    bannerText = `Cash Market Auction in Progress. Awaiting Equilibrium Price... (Current Time: ${timeStr})`;
  } else if (isGoldenWindow) {
    bannerClass = "bg-emerald-950/40 border-emerald-500 animate-pulse text-emerald-200";
    bannerText = `CAS Resolved. F&O Execution Window Open. (Current Time: ${timeStr})`;
  }

  const formatOI = (val: number) => {
    const crores = val / 10000000;
    return `${crores > 0 ? '+' : ''}${crores.toFixed(1)} Cr`;
  };

  const {
    equilibrium_price,
    day_high,
    day_low
  } = data.cas_market_state;

  const range = day_high - day_low;
  // Clamped progress between 0 and 100
  const eqProgress = range > 0 ? Math.max(0, Math.min(100, ((equilibrium_price - day_low) / range) * 100)) : 0;

  return (
    <div className="p-8 space-y-8 bg-zinc-950 min-h-screen text-zinc-100 selection:bg-zinc-800 font-sans">

      {/* Component 1: The CAS Timing Banner */}
      <div className={`w-full p-6 border rounded-xl flex items-center justify-center gap-3 transition-colors duration-500 ${bannerClass}`}>
        <Clock className="w-6 h-6 shrink-0" />
        <h2 className="text-xl font-bold tracking-wide">{bannerText}</h2>
      </div>

      {/* Component 2: The Three Pillars Grid */}
      <div className="grid grid-cols-3 gap-8">

        {/* Pillar 1: MACRO TREND */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-zinc-500 tracking-widest uppercase mb-6">Macro Trend</h3>
            <div className="text-2xl font-semibold tracking-tight text-zinc-200">
              {data.futures_trend.replace('_', ' ')}
            </div>
          </div>
          <div className="mt-8 flex items-center gap-3">
            {data.pillar_macro ? (
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            ) : (
              <XCircle className="w-8 h-8 text-slate-500" />
            )}
            <span className="text-sm font-medium text-zinc-400">
              {data.pillar_macro ? "Condition Met" : "Condition Unmet"}
            </span>
          </div>
        </div>

        {/* Pillar 2: MICRO OI SHIFT */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-zinc-500 tracking-widest uppercase mb-6">Micro OI Shift</h3>
            <div className="space-y-4 font-mono text-xl">
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm font-sans">Call OI:</span>
                <span className="text-rose-400 font-bold">{formatOI(data.post_1pm_oi.call_oi_change)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-400 text-sm font-sans">Put OI:</span>
                <span className="text-emerald-400 font-bold">{formatOI(data.post_1pm_oi.put_oi_change)}</span>
              </div>
            </div>
          </div>
          <div className="mt-8 flex items-center gap-3">
            {data.pillar_micro ? (
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            ) : (
              <XCircle className="w-8 h-8 text-slate-500" />
            )}
            <span className="text-sm font-medium text-zinc-400">
              {data.pillar_micro ? "Bearish Pressure Confirmed" : "Insufficient Shift"}
            </span>
          </div>
        </div>

        {/* Pillar 3: CAS SETTLEMENT */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-zinc-500 tracking-widest uppercase mb-6">CAS Settlement</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm text-zinc-500 font-mono">
                <span>L: {day_low}</span>
                <span className="text-zinc-200">CAS: {equilibrium_price}</span>
                <span>H: {day_high}</span>
              </div>
              <div className="relative w-full h-3 bg-zinc-800 rounded-full overflow-hidden">
                {/* Visual marker of where the price settled in the range */}
                <div
                  className="absolute top-0 bottom-0 w-1 bg-zinc-100 z-10 rounded-full"
                  style={{ left: `${eqProgress}%` }}
                />
                {/* Highlight the bottom 15% as the bearish acceptable zone */}
                <div className="absolute top-0 left-0 bottom-0 bg-rose-500/20" style={{ width: '15%' }} />
              </div>
            </div>
          </div>
          <div className="mt-8 flex items-center gap-3">
            {data.pillar_cas ? (
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            ) : (
              <XCircle className="w-8 h-8 text-slate-500" />
            )}
            <span className="text-sm font-medium text-zinc-400">
              {data.pillar_cas ? "Settled in Lower 15%" : "Settled outside target range"}
            </span>
          </div>
        </div>

      </div>

      {/* Component 3: The Execution Signal Block */}
      <div className="mt-8">
        {data.signal === 'EXECUTE_BTST_PUT' ? (
          <div className="bg-rose-950/30 border-2 border-rose-600 rounded-xl p-8 flex flex-col items-center justify-center text-center space-y-3">
            <h1 className="text-4xl font-black tracking-tight text-rose-500">BTST PUT SIGNAL CONFIRMED.</h1>
            <p className="text-lg text-rose-300 font-medium">Execute F&O Put position immediately. Window closes at {data.deadline}.</p>
          </div>
        ) : (
          <div className="bg-slate-900/50 rounded-xl p-8 flex flex-col items-center justify-center text-center">
            <h1 className="text-2xl font-bold tracking-tight text-slate-500">No Trade. Conditions Unmet.</h1>
            <p className="text-slate-600 mt-2">{data.message}</p>
          </div>
        )}
      </div>

    </div>
  );
};

export default BtstDashboardView;
