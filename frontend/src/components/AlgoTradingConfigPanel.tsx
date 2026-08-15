import React, { useEffect, useState } from 'react';
import { Cpu, Plus, Power, Settings2, Trash2, User } from 'lucide-react';
import { useAlgoConfigStore } from '../stores/algoConfigStore';
import StatusBadge from './StatusBadge';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Underlying = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

export const AlgoTradingConfigPanel: React.FC = () => {
  const { config, setConfig } = useAlgoConfigStore();

  const [mode, setMode] = useState<'SYSTEM' | 'MANUAL'>('SYSTEM');
  const [underlying, setUnderlying] = useState<Underlying>('NIFTY');
  const [capital, setCapital] = useState('');
  const [lotSchedule, setLotSchedule] = useState<string[]>(['2', '3', '5']);
  const [stopLossPct, setStopLossPct] = useState('');
  const [targetPct, setTargetPct] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${baseUrl()}/api/v1/algo-config/status`)
      .then((r) => r.json())
      .then(setConfig)
      .catch((e) => console.error('Failed to fetch algo config status', e));
  }, [setConfig]);

  const addTier = () => setLotSchedule([...lotSchedule, '']);
  const removeTier = (idx: number) => setLotSchedule(lotSchedule.filter((_, i) => i !== idx));
  const updateTier = (idx: number, value: string) =>
    setLotSchedule(lotSchedule.map((v, i) => (i === idx ? value : v)));

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      const body: Record<string, unknown> = { mode };
      if (mode === 'MANUAL') {
        const capitalNum = parseFloat(capital);
        const tiers = lotSchedule.map((v) => parseInt(v, 10)).filter((n) => !isNaN(n) && n > 0);
        if (isNaN(capitalNum) || capitalNum <= 0) {
          setError('Capital must be a positive number.');
          setSaving(false);
          return;
        }
        if (tiers.length === 0) {
          setError('Add at least one pyramid tier (lots to buy).');
          setSaving(false);
          return;
        }
        body.underlying = underlying;
        body.capital = capitalNum;
        body.lot_schedule = tiers;
        if (stopLossPct) body.stop_loss_pct = parseFloat(stopLossPct);
        if (targetPct) body.target_pct = parseFloat(targetPct);
      }

      const response = await fetch(`${baseUrl()}/api/v1/algo-config/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const responseBody = await response.json();
      if (!response.ok) {
        setError(responseBody.detail || 'Configuration rejected.');
      } else {
        setConfig(responseBody);
      }
    } catch {
      setError('Failed to reach the backend — is it running?');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async () => {
    setActionError(null);
    const action = config?.enabled ? 'disable' : 'enable';
    try {
      const response = await fetch(`${baseUrl()}/api/v1/algo-config/${action}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) {
        setActionError(body.detail || `Failed to ${action} algo trading.`);
      } else {
        setConfig(body);
      }
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings2 size={18} className="text-sky-400" />
          <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Algo Trading Configuration</h3>
        </div>
        {config && (
          <div className="flex items-center gap-2">
            <StatusBadge status={config.mode} />
            <StatusBadge status={config.enabled ? 'ENABLED' : 'DISABLED'} />
          </div>
        )}
      </div>

      {/* System vs Manual sub-toggle */}
      <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded p-1 w-fit">
        <button
          onClick={() => setMode('SYSTEM')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-colors ${mode === 'SYSTEM' ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}
        >
          <Cpu size={13} /> System Algo
        </button>
        <button
          onClick={() => setMode('MANUAL')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-colors ${mode === 'MANUAL' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}
        >
          <User size={13} /> Set Manually
        </button>
      </div>

      {mode === 'SYSTEM' ? (
        <p className="text-xs text-zinc-500 font-mono bg-zinc-950/50 border border-zinc-850 rounded px-3 py-2">
          System Algo: each strategy sizes its own positions using its built-in logic, gated only by
          the platform's global risk limits (quantity/position/loss/order caps). No capital budget or
          pyramid schedule is applied.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-xs">
            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 uppercase tracking-wider">Underlying</label>
              <select
                value={underlying}
                onChange={(e) => setUnderlying(e.target.value as Underlying)}
                className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
              >
                <option value="NIFTY">NIFTY</option>
                <option value="BANKNIFTY">BANKNIFTY</option>
                <option value="SENSEX">SENSEX</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 uppercase tracking-wider">Capital to Deploy (₹)</label>
              <input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                placeholder="e.g. 100000"
                className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 uppercase tracking-wider">Stop Loss % (info only)</label>
              <input
                type="number"
                value={stopLossPct}
                onChange={(e) => setStopLossPct(e.target.value)}
                placeholder="e.g. 30"
                className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 uppercase tracking-wider">Target % (info only)</label>
              <input
                type="number"
                value={targetPct}
                onChange={(e) => setTargetPct(e.target.value)}
                placeholder="e.g. 50"
                className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-zinc-500 uppercase tracking-wider">Pyramid Lot Schedule</label>
            <p className="text-[11px] text-zinc-600 font-mono">
              Tier 1 = first buy, Tier 2 = second buy (first pyramid add), Tier 3 = third buy, etc.
              Each number is a lot cap — the algo may buy fewer, never more.
            </p>
            <div className="flex flex-wrap gap-2">
              {lotSchedule.map((value, idx) => (
                <div key={idx} className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5">
                  <span className="text-[10px] text-zinc-500 uppercase font-bold">T{idx + 1}</span>
                  <input
                    type="number"
                    min={1}
                    value={value}
                    onChange={(e) => updateTier(idx, e.target.value)}
                    className="w-14 bg-transparent text-zinc-200 font-mono text-xs outline-none"
                  />
                  <span className="text-[10px] text-zinc-600">lots</span>
                  <button onClick={() => removeTier(idx)} className="text-zinc-600 hover:text-rose-400">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
              <button
                onClick={addTier}
                className="flex items-center gap-1 px-2 py-1.5 bg-zinc-950 border border-dashed border-zinc-700 rounded text-[11px] text-zinc-400 hover:text-zinc-200 hover:border-zinc-500"
              >
                <Plus size={12} /> Add Tier
              </button>
            </div>
          </div>

          <p className="text-[11px] text-amber-400/80 font-mono bg-amber-500/5 border border-amber-500/10 rounded px-3 py-2">
            Capital and the pyramid lot schedule are enforced by the risk engine on every algo decision
            for {underlying}. Stop Loss % / Target % are stored for reference only — automated
            strategies manage their own exit logic internally and do not read these values yet.
          </p>
        </div>
      )}

      {error && (
        <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 py-2.5 bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded hover:bg-sky-500/20 disabled:opacity-50 text-xs font-bold tracking-wider uppercase"
        >
          {saving ? 'Saving…' : 'Save Configuration'}
        </button>
        <button
          onClick={handleToggleEnabled}
          disabled={!config}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded text-xs font-bold tracking-wider uppercase border transition-colors disabled:opacity-50 ${
            config?.enabled
              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20'
              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
          }`}
        >
          <Power size={14} /> {config?.enabled ? 'Disable Algo' : 'Enable Algo'}
        </button>
      </div>

      {actionError && (
        <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">
          {actionError}
        </div>
      )}

      {config && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono pt-2 border-t border-zinc-850">
          <div>
            <span className="text-zinc-500 block">Active Mode</span>
            <span className="text-zinc-200 font-bold">{config.mode}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Underlying</span>
            <span className="text-zinc-200 font-bold">{config.underlying || '--'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Capital Budget</span>
            <span className="text-zinc-200 font-bold">{config.capital !== null ? `₹${config.capital.toLocaleString()}` : '--'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Lot Schedule</span>
            <span className="text-zinc-200 font-bold">{config.lot_schedule.length > 0 ? config.lot_schedule.join(' → ') : '--'}</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default AlgoTradingConfigPanel;
