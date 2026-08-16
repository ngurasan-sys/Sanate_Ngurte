import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Power, TrendingDown, TrendingUp } from 'lucide-react';
import { useOFAOStore } from '../stores/useOFAOStore';
import type { OFAOConfig, OFAOSnapshot } from '../stores/useOFAOStore';
import { useOFAOWebSocket } from '../hooks/useOFAOWebSocket';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TRACKED_INSTRUMENTS = ['NIFTY FUT', 'SENSEX FUT'];

const STATE_LABELS: Record<string, string> = {
  NO_SETUP: 'NO TRADE',
  LOCATION_APPROACHING: 'WATCH',
  LOCATION_REACHED: 'WATCH',
  ABSORPTION_DETECTED: 'ABSORPTION',
  WAITING_FOR_DOMINANCE: 'WAITING FOR CONFIRMATION',
  DOMINANCE_CONFIRMED: 'TRADE NOW',
  SIGNAL_READY: 'TRADE NOW',
  ORDER_SUBMITTED: 'ORDER SUBMITTED',
  ORDER_FILLED: 'FILLED',
  POSITION_ACTIVE: 'ACTIVE',
  TARGET_1: 'TARGET',
  TARGET_2: 'TARGET',
  EXITED: 'EXITED',
  INVALIDATED: 'INVALIDATED',
  CANCELLED: 'INVALIDATED',
};

const STATE_COLORS: Record<string, string> = {
  NO_SETUP: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  LOCATION_APPROACHING: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  LOCATION_REACHED: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  ABSORPTION_DETECTED: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  WAITING_FOR_DOMINANCE: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  DOMINANCE_CONFIRMED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/40',
  SIGNAL_READY: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/40',
  ORDER_SUBMITTED: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
  ORDER_FILLED: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
  POSITION_ACTIVE: 'bg-emerald-600/30 text-emerald-200 border-emerald-600/50',
  TARGET_1: 'bg-emerald-600/30 text-emerald-200 border-emerald-600/50',
  TARGET_2: 'bg-emerald-600/30 text-emerald-200 border-emerald-600/50',
  EXITED: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  INVALIDATED: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
  CANCELLED: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
};

const fmt = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '--' : v.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const InstrumentCard: React.FC<{ snapshot: OFAOSnapshot | undefined; instrumentKey: string }> = ({ snapshot, instrumentKey }) => {
  if (!snapshot) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col items-center justify-center gap-3 min-h-[200px]">
        <Activity className="animate-spin text-zinc-600" size={24} />
        <span className="text-xs text-zinc-500 font-mono uppercase tracking-widest">{instrumentKey} — awaiting data</span>
      </div>
    );
  }

  const label = STATE_LABELS[snapshot.state] || snapshot.state;
  const color = STATE_COLORS[snapshot.state] || STATE_COLORS.NO_SETUP;
  const intent = snapshot.trade_intent;
  const DirectionIcon = snapshot.direction === 'BEAR' ? TrendingDown : TrendingUp;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      <div className="flex items-center justify-between border-b border-zinc-850 pb-4">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider">{snapshot.underlying}</h3>
          <p className="text-xs text-zinc-500 font-mono mt-0.5">{instrumentKey} · LTP {fmt(snapshot.last_price)}</p>
        </div>
        <span className={`px-3 py-1 rounded text-[11px] font-bold font-sans tracking-widest border uppercase ${color}`}>
          {label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 text-xs">
        <div className="space-y-1">
          <span className="text-zinc-500 uppercase tracking-wider font-bold">Direction</span>
          <div className="flex items-center gap-1.5 text-zinc-200 font-mono">
            {snapshot.direction ? <DirectionIcon size={14} className={snapshot.direction === 'BEAR' ? 'text-rose-400' : 'text-emerald-400'} /> : null}
            {snapshot.direction || '--'}
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-zinc-500 uppercase tracking-wider font-bold">Location</span>
          <div className="text-zinc-200 font-mono">{fmt(snapshot.location_price)}</div>
        </div>
        <div className="space-y-1">
          <span className="text-zinc-500 uppercase tracking-wider font-bold">Location Factors</span>
          <div className="text-zinc-400 font-mono text-[11px] truncate">{snapshot.location_reason || '--'}</div>
        </div>
        <div className="space-y-1">
          <span className="text-zinc-500 uppercase tracking-wider font-bold">Absorption Strength</span>
          <div className="text-zinc-200 font-mono">{snapshot.absorption_strength > 0 ? snapshot.absorption_strength.toFixed(0) + '/100' : '--'}</div>
        </div>
      </div>

      {intent && (
        <div className="bg-emerald-950/30 border border-emerald-900/50 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-emerald-400" />
            <span className="text-emerald-300 font-bold text-sm font-sans">
              BUY {intent.underlying} {intent.strike} {intent.option_type}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3 text-[11px] font-mono">
            <div><span className="text-zinc-500 block">Trigger</span><span className="text-zinc-200">{fmt(intent.underlying_trigger)}</span></div>
            <div><span className="text-zinc-500 block">Stop</span><span className="text-rose-400">{fmt(intent.underlying_stop)}</span></div>
            <div><span className="text-zinc-500 block">Target</span><span className="text-emerald-400">{fmt(intent.underlying_target)}</span></div>
            <div><span className="text-zinc-500 block">R:R</span><span className="text-zinc-200">{intent.risk_reward.toFixed(2)}</span></div>
            <div><span className="text-zinc-500 block">Score</span><span className="text-zinc-200">{intent.score}/{intent.score_max}</span></div>
            <div><span className="text-zinc-500 block">Confidence</span><span className="text-zinc-200">{intent.confidence}</span></div>
          </div>
          <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">{intent.reason}</p>
          <p className="text-[10px] text-zinc-600 font-mono">setup_id: {intent.setup_id}</p>
        </div>
      )}
    </div>
  );
};

export const OFAOView: React.FC = () => {
  useOFAOWebSocket();
  const { snapshots, config, connectionStatus, setConfig } = useOFAOStore();

  const [threshold, setThreshold] = useState('70');
  const [ratio, setRatio] = useState('400');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${baseUrl()}/api/v1/ofao/config`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body: OFAOConfig) => {
        setConfig(body);
        setThreshold(String(body.absorption_strength_threshold));
        setRatio(String(body.imbalance_ratio_pct));
      })
      .catch((e) => console.error('Failed to fetch OFAO config', e));
  }, [setConfig]);

  const toggleEnabled = async () => {
    setBusy(true);
    setError(null);
    try {
      const endpoint = config?.enabled ? 'disable' : 'enable';
      const response = await fetch(`${baseUrl()}/api/v1/ofao/${endpoint}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) {
        setError(body.detail || 'Failed to toggle OFAO.');
      } else {
        setConfig(body);
      }
    } catch {
      setError('Failed to reach the backend — is it running?');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveThresholds = async () => {
    if (!config) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/ofao/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...config,
          absorption_strength_threshold: parseFloat(threshold),
          imbalance_ratio_pct: parseFloat(ratio),
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.detail || 'Failed to save configuration.');
      } else {
        setConfig(body);
      }
    } catch {
      setError('Failed to reach the backend — is it running?');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 select-none">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Order Flow Absorption Options (OFAO)</h2>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">
            Context + Location + Absorption + Dominance Shift + Confirmation → option-buying TradeIntent, on the existing risk/execution pipeline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connectionStatus === 'CONNECTED' ? 'bg-emerald-400' : 'bg-rose-400'}`} />
          <span className="text-[10px] text-zinc-500 font-mono uppercase">{connectionStatus}</span>
        </div>
      </div>

      <div className="bg-amber-950/30 border border-amber-900/50 rounded-lg px-4 py-2.5 text-xs text-amber-300 font-mono">
        SIMULATED DATA — this strategy evaluates real order-flow logic, but the only tick source feeding it today is the
        footprint module's local random-walk simulator (no real Level 2 futures depth is wired into this app yet).
        DRY_RUN is the default execution mode regardless — no real order reaches a broker without both the execution
        engine's LIVE arm switch and this strategy's own enable toggle below.
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col lg:flex-row lg:items-center gap-6 lg:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={toggleEnabled}
            disabled={busy}
            className={`flex items-center gap-2 px-4 py-2 rounded text-xs font-bold uppercase tracking-wider transition-colors ${
              config?.enabled ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
            }`}
          >
            <Power size={14} />
            {config?.enabled ? 'Enabled' : 'Disabled'}
          </button>
          {!config?.enabled && (
            <span className="text-[11px] text-zinc-500 font-mono">No signals will be generated while disabled.</span>
          )}
        </div>

        <div className="flex items-center gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Absorption Threshold</span>
            <input
              type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 font-mono w-20"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Imbalance Ratio %</span>
            <select
              value={ratio} onChange={(e) => setRatio(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 font-mono"
            >
              {[200, 300, 400, 500].map((r) => <option key={r} value={r}>{r}%</option>)}
            </select>
          </div>
          <button
            onClick={handleSaveThresholds}
            disabled={busy}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-bold uppercase tracking-wider px-3 py-2 rounded transition-colors self-end"
          >
            Save
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-rose-400 font-mono">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {TRACKED_INSTRUMENTS.map((key) => (
          <InstrumentCard key={key} snapshot={snapshots[key]} instrumentKey={key} />
        ))}
      </div>
    </div>
  );
};

export default OFAOView;
