import React, { useEffect, useState } from 'react';
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Clock } from 'lucide-react';

interface ExpiryReversalSignal {
  strategy_id: string;
  instrument: string;
  action: string;
  direction?: string | null;
  lots: number;
  stop_loss?: number | null;
  reason: string;
  timestamp: string;
}

interface ExpiryReversalState {
  instrument: string;
  status?: string;
  position_state?: string;
  direction?: string | null;
  lots_held?: number;
  avg_entry_price?: number;
  current_sl?: number;
  tier_1_status?: string;
  tier_2_status?: string;
  tier_3_status?: string;
  partial_exit_done?: boolean;
  breakeven_done?: boolean;
  weak_move_active?: boolean;
  skipped_late_session?: boolean;
}

function isSignal(data: unknown): data is ExpiryReversalSignal {
  return typeof data === 'object' && data !== null && 'action' in data;
}

const TierBadge: React.FC<{ label: string; status?: string }> = ({ label, status }) => {
  const s = status || 'PENDING';
  let colorClass = 'bg-zinc-800 text-zinc-500 border-zinc-700';
  if (s === 'FILLED') colorClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  else if (s === 'CANCELLED') colorClass = 'bg-zinc-800 text-zinc-600 border-zinc-700 line-through';

  return (
    <div className={`flex flex-col items-center gap-1 px-4 py-3 rounded-xl border ${colorClass}`}>
      <span className="text-[10px] uppercase tracking-widest font-bold">{label}</span>
      <span className="text-xs font-mono">{s}</span>
    </div>
  );
};

export const ExpiryReversalView: React.FC = () => {
  const [state, setState] = useState<ExpiryReversalState | null>(null);
  const [signals, setSignals] = useState<ExpiryReversalSignal[]>([]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/ws/expiry_reversal');

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (isSignal(parsed)) {
            setSignals((prev) => [parsed, ...prev].slice(0, 10));
          } else {
            setState(parsed);
          }
        } catch (e) {
          console.error('Failed to parse expiry_reversal message', e);
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

  const noData = !state || state.status === 'NO_ACTIVE_INSTRUMENT_STATE';
  const direction = state?.direction;
  const isBearish = direction === 'BEARISH';

  return (
    <div className="p-8 space-y-8 bg-zinc-950 min-h-screen text-zinc-100 font-sans select-none">
      <div>
        <h2 className="text-zinc-100 font-bold text-lg uppercase tracking-wider">Expiry Day Reversal Setup</h2>
        <p className="text-xs text-zinc-400 mt-0.5">
          Weak short-covering up-moves interrupted by a confirmed 3-minute Call/Put OI shift, entered via a
          3-tier ladder with break-even profit protection and a late-session/ATR-exhaustion skip filter.
        </p>
      </div>

      {noData ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col items-center justify-center text-center gap-3">
          <div className="w-8 h-8 border-4 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
          <p className="text-zinc-400">Waiting for instrument state — no candles processed yet today.</p>
        </div>
      ) : (
        <>
          {state?.skipped_late_session && (
            <div className="bg-amber-950/30 border border-amber-800 rounded-xl p-4 flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
              <p className="text-sm text-amber-200">
                Late-session entry skipped — expiry day, day range has already used up most of the average
                daily range. Risk/reward unfavorable despite OI confirmation.
              </p>
            </div>
          )}

          {state?.weak_move_active && state?.position_state === 'WAITING' && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center gap-3">
              <Clock className="w-5 h-5 text-zinc-500 shrink-0" />
              <p className="text-sm text-zinc-400">
                Weak move detected (short-covering driven, small candles) — reduced sizing applies if this
                turns into an entry.
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col justify-between">
              <div>
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-6">Position</h3>
                <div className="flex items-center gap-3">
                  {isBearish ? (
                    <ArrowDownRight className="w-8 h-8 text-rose-500" />
                  ) : direction === 'BULLISH' ? (
                    <ArrowUpRight className="w-8 h-8 text-emerald-500" />
                  ) : null}
                  <span className="text-2xl font-semibold tracking-tight">
                    {state?.position_state?.replace(/_/g, ' ') || 'WAITING'}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 mt-6 font-mono text-sm">
                  <div>
                    <span className="text-zinc-500 text-xs block">Direction</span>
                    <span className="font-bold">{direction || '-'}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 text-xs block">Lots Held</span>
                    <span className="font-bold">{state?.lots_held ?? 0}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 text-xs block">Avg Entry</span>
                    <span className="font-bold">{state?.avg_entry_price ? state.avg_entry_price.toFixed(2) : '-'}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 text-xs block">Stop Loss</span>
                    <span className="font-bold">{state?.current_sl ? state.current_sl.toFixed(2) : '-'}</span>
                  </div>
                </div>
              </div>
              <div className="mt-8 flex items-center gap-4 text-xs">
                <span className={`px-2 py-1 rounded border ${state?.partial_exit_done ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}>
                  Partial Exit: {state?.partial_exit_done ? 'DONE' : 'PENDING'}
                </span>
                <span className={`px-2 py-1 rounded border ${state?.breakeven_done ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}>
                  Break-even SL: {state?.breakeven_done ? 'SET' : 'PENDING'}
                </span>
              </div>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-6">Laddered Entry (3 Tiers)</h3>
              <div className="grid grid-cols-3 gap-4">
                <TierBadge label="Tier 1 (2 lots)" status={state?.tier_1_status} />
                <TierBadge label="Tier 2 (2 lots)" status={state?.tier_2_status} />
                <TierBadge label="Tier 3 (4 lots)" status={state?.tier_3_status} />
              </div>
            </div>
          </div>
        </>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8">
        <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-6">Recent Signals</h3>
        {signals.length === 0 ? (
          <p className="text-zinc-600 text-sm">No signals yet.</p>
        ) : (
          <div className="space-y-2">
            {signals.map((s, idx) => (
              <div key={idx} className="flex items-center justify-between font-mono text-xs bg-zinc-950 rounded-lg px-4 py-3 border border-zinc-800">
                <span className="font-bold text-zinc-200">{s.action}</span>
                <span className="text-zinc-500">{s.direction || '-'}</span>
                <span className="text-zinc-500">{s.lots > 0 ? `${s.lots} lots` : ''}</span>
                <span className="text-zinc-400 truncate max-w-xs">{s.reason}</span>
                <span className="text-zinc-600">{new Date(s.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ExpiryReversalView;
