import React, { useEffect, useState } from 'react';
import { AlertTriangle, Power, Radio, Settings2, X, Zap } from 'lucide-react';
import { useCASDislocationStore } from '../stores/casDislocationStore';
import { useCASDislocationWebSocket } from '../hooks/useCASDislocationWebSocket';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Underlying = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

const fmtPrice = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? '--' : v.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined ? '--' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;

const StateBadge: React.FC<{ state: string }> = ({ state }) => {
  const styles: Record<string, string> = {
    PRE_CAS: 'bg-white/[0.06] text-slate-400 border-white/[0.07]',
    CAS_FREEZE: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
    DISLOCATION: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    SIGNAL: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/40',
    VOLATILITY_SHOCK: 'bg-rose-500/10 text-rose-500 border-rose-500/50',
    INACTIVE: 'bg-white/[0.04] text-slate-500 border-white/[0.07]',
  };
  return (
    <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold font-sans tracking-widest border uppercase ${styles[state] || styles.INACTIVE}`}>
      {state.replace('_', ' ')}
    </span>
  );
};

export const CASDislocationView: React.FC = () => {
  useCASDislocationWebSocket();
  const { reading, config, positions, connectionStatus, setConfig } = useCASDislocationStore();

  const [underlying, setUnderlying] = useState<Underlying>('NIFTY');
  const [lots, setLots] = useState('1');
  const [maxHold, setMaxHold] = useState('90');
  const [scoreAlert, setScoreAlert] = useState('60');
  const [scoreExecute, setScoreExecute] = useState('85');
  const [autoExecute, setAutoExecute] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${baseUrl()}/api/v1/cas-dislocation/config`)
      .then((r) => r.json())
      .then(setConfig)
      .catch((e) => console.error('Failed to fetch CAS config', e));
  }, [setConfig]);

  const handleSave = async () => {
    setSaveError(null);
    setBusy(true);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/cas-dislocation/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          lots: parseInt(lots, 10) || 0,
          max_hold_seconds: parseInt(maxHold, 10) || 0,
          min_score_to_alert: parseInt(scoreAlert, 10) || 0,
          min_score_to_execute: parseInt(scoreExecute, 10) || 0,
          auto_execute: autoExecute,
        }),
      });
      const body = await response.json();
      if (!response.ok) setSaveError(body.detail || 'Configuration rejected.');
      else setConfig(body);
    } catch {
      setSaveError('Failed to reach the backend — is it running?');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleEnabled = async () => {
    setActionError(null);
    const action = config?.enabled ? 'disable' : 'enable';
    try {
      const response = await fetch(`${baseUrl()}/api/v1/cas-dislocation/${action}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) setActionError(body.detail || `Failed to ${action}.`);
      else setConfig(body);
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  const handleExecute = async () => {
    setActionError(null);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/cas-dislocation/execute`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) setActionError(body.detail || 'Execute rejected.');
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  const handleAbort = async (positionId: string) => {
    setActionError(null);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/cas-dislocation/abort/${positionId}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) setActionError(body.detail || 'Abort rejected.');
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  const state = reading?.state || 'INACTIVE';
  const activePositions = positions.filter((p) => p.status === 'OPEN' || p.status === 'PENDING');

  return (
    <div className="min-h-screen bg-[#0B0E14] text-slate-200 p-6 space-y-6 select-none">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Radio size={20} className="text-sky-400" />
            <h1 className="font-sans font-bold text-lg tracking-wide text-slate-100">CAS DISLOCATION ENGINE</h1>
            <StateBadge state={state} />
          </div>
          <p className="text-xs text-slate-500 font-sans mt-1 max-w-2xl">
            Independent expiry-day module — its own config, its own arm switch, no strategy engine wiring.
            Tracks the gap between the frozen cash spot (~15:15 IST) and the still-trading futures/options
            market. Executes only through the platform's normal risk/execution pipeline: DRY_RUN by default,
            needs the broker LIVE arm switch, and its own "Enable" toggle below.
          </p>
        </div>
        <span className={`text-[11px] font-mono uppercase tracking-widest ${connectionStatus === 'CONNECTED' ? 'text-emerald-400' : 'text-slate-500'}`}>
          WS: {connectionStatus}
        </span>
      </div>

      {/* Config */}
      <div className="bg-[#111622] border border-white/[0.07] rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-slate-400" />
            <h2 className="font-sans font-bold text-xs uppercase tracking-widest text-slate-300">Configuration</h2>
          </div>
          {config && (
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${config.enabled ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-white/[0.06] text-slate-500 border-white/[0.07]'}`}>
              {config.enabled ? 'ARMED' : 'DISARMED'}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-xs font-mono">
          <div className="flex flex-col gap-1">
            <label className="text-slate-500 uppercase tracking-wider font-sans">Underlying</label>
            <select value={underlying} onChange={(e) => setUnderlying(e.target.value as Underlying)}
              className="bg-[#0B0E14] border border-white/[0.07] text-slate-200 rounded px-2 py-1.5 outline-none">
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
              <option value="SENSEX">SENSEX</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-slate-500 uppercase tracking-wider font-sans">Lot Size (lots)</label>
            <input type="number" min={1} value={lots} onChange={(e) => setLots(e.target.value)}
              className="bg-[#0B0E14] border border-white/[0.07] text-slate-200 rounded px-2 py-1.5 outline-none" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-slate-500 uppercase tracking-wider font-sans">Max Hold (sec)</label>
            <input type="number" min={1} value={maxHold} onChange={(e) => setMaxHold(e.target.value)}
              className="bg-[#0B0E14] border border-white/[0.07] text-slate-200 rounded px-2 py-1.5 outline-none" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-slate-500 uppercase tracking-wider font-sans">Alert Score</label>
            <input type="number" min={0} max={100} value={scoreAlert} onChange={(e) => setScoreAlert(e.target.value)}
              className="bg-[#0B0E14] border border-white/[0.07] text-slate-200 rounded px-2 py-1.5 outline-none" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-slate-500 uppercase tracking-wider font-sans">Execute Score</label>
            <input type="number" min={0} max={100} value={scoreExecute} onChange={(e) => setScoreExecute(e.target.value)}
              className="bg-[#0B0E14] border border-white/[0.07] text-slate-200 rounded px-2 py-1.5 outline-none" />
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs font-sans text-slate-400 cursor-pointer w-fit">
          <input type="checkbox" checked={autoExecute} onChange={(e) => setAutoExecute(e.target.checked)} className="accent-emerald-500" />
          Auto-execute (fires without manual [EXECUTE] confirmation — off by default, extra safety layer)
        </label>

        {saveError && <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">{saveError}</div>}
        {actionError && <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">{actionError}</div>}

        <div className="flex gap-2">
          <button onClick={handleSave} disabled={busy}
            className="flex-1 py-2.5 bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-lg hover:bg-sky-500/20 disabled:opacity-50 text-xs font-bold tracking-wider uppercase font-sans">
            {busy ? 'Saving…' : 'Save Configuration'}
          </button>
          <button onClick={handleToggleEnabled} disabled={!config}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold tracking-wider uppercase font-sans border disabled:opacity-50 ${
              config?.enabled ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
            }`}>
            <Power size={14} /> {config?.enabled ? 'Disable' : 'Enable'}
          </button>
        </div>
      </div>

      {/* Live radar / shock warning */}
      {state === 'VOLATILITY_SHOCK' ? (
        <div className="bg-[#111622] border border-rose-500/50 rounded-2xl p-8 space-y-4 text-center">
          <div className="flex items-center justify-center gap-2 text-rose-500">
            <AlertTriangle size={20} />
            <h2 className="font-sans font-bold text-sm tracking-widest uppercase">CAS Volatility Shock</h2>
          </div>
          <div className="flex justify-center gap-8 font-mono tabular-nums text-lg">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">CE</div>
              <div className="text-rose-400">₹{fmtPrice(reading?.ce_bid)} → ₹{fmtPrice(reading?.ce_ask)}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">PE</div>
              <div className="text-rose-400">₹{fmtPrice(reading?.pe_bid)} → ₹{fmtPrice(reading?.pe_ask)}</div>
            </div>
          </div>
          <p className="text-xs text-slate-400 font-sans">BOTH-SIDE REPRICING — possible liquidity / stale-quote event, not a directional dislocation.</p>
          <div className="inline-block px-4 py-1.5 bg-rose-500/10 text-rose-500 border border-rose-500/50 rounded-full text-xs font-bold uppercase tracking-widest font-sans">
            Trade Blocked
          </div>
        </div>
      ) : (
        <div className="bg-[#111622] border border-white/[0.07] rounded-2xl p-6 space-y-5">
          {/* Anchor row */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/[0.07]">
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider font-sans">CAS Spot</div>
              <div className="font-mono tabular-nums text-2xl text-slate-100">
                {fmtPrice(reading?.frozen_spot)}
                {reading?.frozen_spot != null && <span className="ml-2 text-[10px] text-sky-400 align-middle">[FROZEN]</span>}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider font-sans">Future</div>
              <div className="font-mono tabular-nums text-2xl text-slate-100">
                {fmtPrice(reading?.future_price)}
                {reading?.future_displacement != null && (
                  <span className={`ml-2 text-sm ${reading.future_displacement >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {reading.future_displacement >= 0 ? '▲' : '▼'} {fmtPrice(Math.abs(reading.future_displacement), 1)}
                  </span>
                )}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider font-sans">Future Velocity</div>
              <div className="font-mono tabular-nums text-lg text-slate-200">
                {reading?.future_velocity != null ? `${fmtPrice(reading.future_velocity, 1)} pts/s` : '--'}
              </div>
            </div>
          </div>

          {state === 'PRE_CAS' || state === 'INACTIVE' ? (
            <div className="text-center py-8 text-slate-500 font-mono text-xs uppercase tracking-wider">
              {reading?.reason || 'Waiting for the CAS window (14:55–15:20 IST on an expiry day)…'}
            </div>
          ) : (
            <>
              {/* ATM strike CE/PE */}
              <div>
                <div className="text-[11px] text-slate-500 uppercase tracking-wider font-sans mb-2">ATM {fmtPrice(reading?.atm_strike, 0)}</div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-[#182030] rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-sans font-bold text-sm text-emerald-400">CE</span>
                      {reading?.ce_dislocation_pct != null && reading.ce_theoretical != null && reading.ce_ask != null && reading.ce_theoretical > reading.ce_ask && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-500 border border-rose-500/50 uppercase tracking-wider">
                          Gamma Squeeze Detected
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-3 gap-2 font-mono tabular-nums text-xs">
                      <div><span className="text-slate-500 block text-[10px]">BID</span>{fmtPrice(reading?.ce_bid)}</div>
                      <div><span className="text-slate-500 block text-[10px]">ASK</span>{fmtPrice(reading?.ce_ask)}</div>
                      <div><span className="text-slate-500 block text-[10px]">FAIR</span>{fmtPrice(reading?.ce_theoretical)}</div>
                    </div>
                    <div className="text-xs font-mono">
                      <span className="text-slate-500">Dislocation: </span>
                      <span className={reading?.ce_dislocation_pct != null && reading.ce_dislocation_pct > 0 ? 'text-emerald-400' : 'text-slate-400'}>
                        {fmtPct(reading?.ce_dislocation_pct)}
                      </span>
                    </div>
                  </div>
                  <div className="bg-[#182030] rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-sans font-bold text-sm text-rose-400">PE</span>
                      {reading?.pe_dislocation_pct != null && reading.pe_theoretical != null && reading.pe_ask != null && reading.pe_theoretical > reading.pe_ask && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-500 border border-rose-500/50 uppercase tracking-wider">
                          Gamma Squeeze Detected
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-3 gap-2 font-mono tabular-nums text-xs">
                      <div><span className="text-slate-500 block text-[10px]">BID</span>{fmtPrice(reading?.pe_bid)}</div>
                      <div><span className="text-slate-500 block text-[10px]">ASK</span>{fmtPrice(reading?.pe_ask)}</div>
                      <div><span className="text-slate-500 block text-[10px]">FAIR</span>{fmtPrice(reading?.pe_theoretical)}</div>
                    </div>
                    <div className="text-xs font-mono">
                      <span className="text-slate-500">Dislocation: </span>
                      <span className={reading?.pe_dislocation_pct != null && reading.pe_dislocation_pct > 0 ? 'text-emerald-400' : 'text-slate-400'}>
                        {fmtPct(reading?.pe_dislocation_pct)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Secondary metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-sans">IV Shift CE</span>
                  {fmtPct(reading?.iv_shift_ce)}
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-sans">IV Shift PE</span>
                  {fmtPct(reading?.iv_shift_pe)}
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-sans">Volume Accel</span>
                  {reading?.volume_acceleration != null ? `${reading.volume_acceleration.toFixed(1)}x` : '--'}
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-sans">CAS Score</span>
                  <span className="text-slate-100 font-bold">{reading?.score ?? 0} / 100</span>
                </div>
              </div>

              {reading?.reason && <p className="text-[11px] text-slate-500 font-mono border-t border-white/[0.07] pt-3">{reading.reason}</p>}

              {/* Execution block */}
              {state === 'SIGNAL' && reading?.signal !== 'NONE' && (
                <div className="rounded-xl p-5 ring-2 ring-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.2)] bg-emerald-500/5 space-y-3">
                  <div className="flex items-center gap-2 text-emerald-400">
                    <Zap size={16} />
                    <span className="font-sans font-bold text-sm uppercase tracking-wider">{reading?.signal.replace('_', ' ')} Candidate</span>
                  </div>
                  <p className="text-xs text-slate-300 font-mono">
                    Score {reading?.score}/100 — Max hold: {config?.max_hold_seconds ?? 90}s.
                    {config?.auto_execute ? ' Auto-execute is ON.' : ' Manual confirmation required.'}
                  </p>
                  <button onClick={handleExecute}
                    className="w-full py-2.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-lg hover:bg-emerald-500/30 text-xs font-bold tracking-widest uppercase font-sans">
                    Execute Squeeze Setup
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Positions */}
      <div className="bg-[#111622] border border-white/[0.07] rounded-2xl p-6">
        <h2 className="font-sans font-bold text-xs uppercase tracking-widest text-slate-300 mb-4">CAS Positions</h2>
        {activePositions.length === 0 ? (
          <div className="text-center py-6 text-slate-500 font-mono text-xs uppercase tracking-wider border border-dashed border-white/[0.07] rounded-xl">
            No Active CAS Positions
          </div>
        ) : (
          <div className="space-y-2">
            {activePositions.map((p) => (
              <div key={p.position_id} className="flex items-center justify-between bg-[#182030] rounded-xl p-4 font-mono text-xs">
                <div>
                  <span className={p.option_type === 'CE' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {p.underlying} {p.strike} {p.option_type}
                  </span>
                  <span className="text-slate-500 ml-2">({p.lots} lots, qty {p.quantity})</span>
                  <span className="ml-3 px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400 text-[10px] uppercase">{p.status}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-slate-400">Entry ₹{fmtPrice(p.entry_price)}</span>
                  {p.status === 'OPEN' && (
                    <button onClick={() => handleAbort(p.position_id)}
                      className="px-2 py-1 bg-white/[0.06] text-slate-300 border border-white/[0.07] rounded hover:bg-rose-500/20 hover:text-rose-400 text-[10px] font-bold uppercase flex items-center gap-1">
                      <X size={10} /> Abort
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default CASDislocationView;
