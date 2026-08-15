import React, { useCallback, useEffect, useState } from 'react';
import StatusBadge from '../components/StatusBadge';
import MetricCard from '../components/MetricCard';
import { ShieldAlert, Power, Lock, Unlock } from 'lucide-react';

interface ExecutionStatus {
  env_mode: 'DRY_RUN' | 'SANDBOX' | 'LIVE';
  resolved_mode: 'DRY_RUN' | 'SANDBOX' | 'LIVE';
  armed: boolean;
  armed_at: string | null;
  armed_note: string | null;
  halted_reason: string | null;
  risk_limits: {
    max_quantity_per_order: number;
    max_open_positions: number;
    max_daily_loss: number;
    max_daily_orders: number;
    market_open: string;
    market_close: string;
    allow_trading: boolean;
  };
  risk_state: {
    open_positions: number;
    realized_pnl_today: number;
    orders_placed_today: number;
  };
}

const ARM_PHRASE = 'ARM LIVE TRADING';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const ExecutionControlView: React.FC = () => {
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState('');
  const [armNote, setArmNote] = useState('');
  const [haltReason, setHaltReason] = useState('');
  const [busy, setBusy] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/execution/status`);
      if (!res.ok) throw new Error(`Status fetch failed (${res.status})`);
      setStatus(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach backend');
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const post = async (path: string, body?: unknown) => {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || `Request failed (${res.status})`);
        return;
      }
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const handleArm = () => {
    post('/api/v1/execution/arm', { confirm: confirmText, note: armNote || null });
    setConfirmText('');
  };

  const handleDisarm = () => post('/api/v1/execution/disarm');
  const handleHalt = () => {
    post('/api/v1/execution/halt', { reason: haltReason || 'Manual kill switch' });
    setHaltReason('');
  };
  const handleResume = () => post('/api/v1/execution/resume');

  const liveFullyArmed = status?.resolved_mode === 'LIVE';
  const envIsLive = status?.env_mode === 'LIVE';

  return (
    <div className="space-y-6 select-none pb-12">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">
          Execution Control
        </h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">
          Two independent switches gate real-money order placement. Both must be set for a
          LIVE order to ever reach the broker.
        </p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Status overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          label="Env Mode (.env)"
          value={status?.env_mode ?? '—'}
          subValue={envIsLive ? 'LIVE configured' : 'switch 1'}
          subValueColor={envIsLive ? 'bearish' : 'muted'}
        />
        <MetricCard
          label="Runtime Arm Switch"
          value={status?.armed ? 'ARMED' : 'DISARMED'}
          subValue="switch 2 (resets on restart)"
          subValueColor={status?.armed ? 'bearish' : 'bullish'}
        />
        <MetricCard
          label="Resolved Execution Mode"
          value={status?.resolved_mode ?? '—'}
          subValue={liveFullyArmed ? 'REAL ORDERS WILL BE SENT' : 'safe'}
          subValueColor={liveFullyArmed ? 'bearish' : 'bullish'}
        />
        <MetricCard
          label="Kill Switch"
          value={status?.halted_reason ? 'HALTED' : 'CLEAR'}
          subValue={status?.halted_reason ?? 'trading not blocked'}
          subValueColor={status?.halted_reason ? 'bearish' : 'bullish'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Arm / Disarm panel */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Power size={18} className="text-rose-400" />
              <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
                Runtime Arm Switch
              </h3>
            </div>
            <StatusBadge status={status?.armed ? 'ARMED' : 'DISARMED'} />
          </div>

          <p className="text-xs text-zinc-400">
            Arming this switch is only the second of two requirements. LIVE orders also require{' '}
            <code className="text-zinc-300">UPSTOX_EXECUTION_MODE=LIVE</code> set in{' '}
            <code className="text-zinc-300">backend/.env</code>, which this panel cannot change.
            Current env mode is <span className="font-bold text-zinc-200">{status?.env_mode ?? '—'}</span>.
          </p>

          {!status?.armed ? (
            <div className="space-y-2">
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block">
                Type <span className="text-zinc-300 font-bold">{ARM_PHRASE}</span> to arm
              </label>
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={ARM_PHRASE}
                className="w-full bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono text-xs rounded px-3 py-2 outline-none focus:border-rose-500/50"
              />
              <input
                value={armNote}
                onChange={(e) => setArmNote(e.target.value)}
                placeholder="Optional note (e.g. reason for arming)"
                className="w-full bg-zinc-950 border border-zinc-800 text-zinc-400 font-mono text-xs rounded px-3 py-2 outline-none focus:border-zinc-700"
              />
              <button
                onClick={handleArm}
                disabled={busy || confirmText !== ARM_PHRASE}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded hover:bg-rose-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold"
              >
                <Unlock size={14} /> ARM LIVE TRADING
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {status.armed_at && (
                <p className="text-xs text-zinc-500 font-mono">
                  Armed at {new Date(status.armed_at).toLocaleString()}
                  {status.armed_note ? ` — ${status.armed_note}` : ''}
                </p>
              )}
              <button
                onClick={handleDisarm}
                disabled={busy}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold"
              >
                <Lock size={14} /> DISARM
              </button>
            </div>
          )}
        </div>

        {/* Kill switch panel */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert size={18} className="text-amber-400" />
              <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
                Risk Kill Switch
              </h3>
            </div>
            <StatusBadge status={status?.halted_reason ? 'HALTED' : 'CLEAR'} />
          </div>

          <p className="text-xs text-zinc-400">
            Halting blocks every new decision from reaching execution regardless of the arm
            switch above. Use this to stop trading immediately without touching env config.
          </p>

          {!status?.halted_reason ? (
            <div className="space-y-2">
              <input
                value={haltReason}
                onChange={(e) => setHaltReason(e.target.value)}
                placeholder="Reason for halting (optional)"
                className="w-full bg-zinc-950 border border-zinc-800 text-zinc-400 font-mono text-xs rounded px-3 py-2 outline-none focus:border-amber-500/50"
              />
              <button
                onClick={handleHalt}
                disabled={busy}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded hover:bg-amber-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold"
              >
                HALT TRADING
              </button>
            </div>
          ) : (
            <button
              onClick={handleResume}
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-bold"
            >
              RESUME TRADING
            </button>
          )}
        </div>
      </div>

      {/* Risk limits (read-only) */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
        <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
          Active Risk Limits
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 text-xs font-mono">
          <div>
            <span className="text-zinc-500 block">Max Qty / Order</span>
            <span className="text-zinc-200 font-bold">{status?.risk_limits.max_quantity_per_order ?? '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Open Positions</span>
            <span className="text-zinc-200 font-bold">{status?.risk_limits.max_open_positions ?? '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Daily Loss</span>
            <span className="text-zinc-200 font-bold">₹{status?.risk_limits.max_daily_loss ?? '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Daily Orders</span>
            <span className="text-zinc-200 font-bold">{status?.risk_limits.max_daily_orders ?? '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Market Hours</span>
            <span className="text-zinc-200 font-bold">
              {status?.risk_limits.market_open}–{status?.risk_limits.market_close}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block">Orders Placed Today</span>
            <span className="text-zinc-200 font-bold">{status?.risk_state.orders_placed_today ?? '—'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExecutionControlView;
