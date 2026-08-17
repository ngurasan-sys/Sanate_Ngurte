import React, { useState, useMemo } from 'react';
import { LayoutGrid, Search, RefreshCw, Play, Square, PowerOff, Settings2, X } from 'lucide-react';
import { useStrategyStore } from '../stores/strategyStore';
import type { Strategy, ExecutionMode, TradingMode } from '../stores/strategyStore';
import { useStrategyControl } from '../hooks/useStrategyControl';
import type { ReadinessResult } from '../hooks/useStrategyControl';
import MetricCard from './MetricCard';
import StatusBadge from './StatusBadge';

type FilterKey = 'ALL' | 'RUNNING' | 'OFF' | 'BLOCKED' | 'POSITION_ACTIVE';

const FILTERS: FilterKey[] = ['ALL', 'RUNNING', 'OFF', 'BLOCKED', 'POSITION_ACTIVE'];

// Reuses the exact inline segmented-control markup already established in
// AlgoTradingConfigPanel.tsx / AlgoDashboardView.tsx (no dedicated toggle
// component exists in this codebase — replicate rather than invent).
//
// Literal class strings only — Tailwind's JIT purge only keeps classes it
// can find as complete static strings in source, so `bg-${color}-500/20`
// would silently vanish from the production build.
const SEGMENT_ACTIVE_CLASSES: Record<string, string> = {
  rose: 'bg-rose-500/20 text-rose-400 border border-rose-500/30',
  sky: 'bg-sky-500/20 text-sky-400 border border-sky-500/30',
  amber: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
};

const Segmented: React.FC<{
  options: { value: string; label: string; color: 'rose' | 'sky' | 'amber' }[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}> = ({ options, value, onChange, disabled }) => (
  <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded p-1">
    {options.map((opt) => (
      <button
        key={opt.value}
        type="button"
        disabled={disabled}
        aria-pressed={value === opt.value}
        onClick={() => onChange(opt.value)}
        className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
          value === opt.value ? SEGMENT_ACTIVE_CLASSES[opt.color] : 'text-zinc-500 hover:text-zinc-300'
        }`}
      >
        {opt.label}
      </button>
    ))}
  </div>
);

function formatPnl(pnl: number | null): { text: string; color: 'bullish' | 'bearish' | 'neutral' } {
  if (pnl === null || pnl === undefined) return { text: '—', color: 'neutral' };
  const sign = pnl >= 0 ? '+' : '';
  return { text: `${sign}${pnl.toFixed(2)}R`, color: pnl >= 0 ? 'bullish' : 'bearish' };
}

function healthFromStatus(status: string, blockedReason: string | null): { label: string; badge: string } {
  if (status === 'BLOCKED' || status === 'ERROR') return { label: 'BLOCKED', badge: 'BLOCKED' };
  if (status === 'DISCONNECTED' || status === 'DATA_STALE') return { label: 'OFFLINE', badge: 'DISCONNECTED' };
  if (status === 'RUNNING' || status === 'POSITION_ACTIVE' || status === 'SIGNAL') return { label: 'HEALTHY', badge: 'ACTIVE' };
  return { label: blockedReason ? 'WARNING' : 'OFFLINE', badge: blockedReason ? 'WARNING' : 'OFF' };
}

// Confirmation content per the spec's START flow — real backend
// validation still happens on submit regardless of what's shown here.
function startConfirmCopy(strategy: Strategy): { title: string; lines: string[]; cta: string } {
  if (strategy.executionMode === 'ALGO' && strategy.tradingMode === 'AUTO') {
    return {
      title: `START ${strategy.name}`,
      lines: [
        'Execution: ALGO TRADE', 'Trading Mode: AUTO',
        'This strategy may automatically submit LIVE orders when conditions are satisfied.',
      ],
      cta: 'START ALGO',
    };
  }
  if (strategy.executionMode === 'PAPER' && strategy.tradingMode === 'AUTO') {
    return {
      title: `START ${strategy.name}`,
      lines: ['Execution: PAPER TRADE', 'Trading Mode: AUTO', 'No live orders will be submitted.'],
      cta: 'START PAPER',
    };
  }
  return {
    title: `START ${strategy.name}`,
    lines: ['Trading Mode: MANUAL', 'The strategy will generate signals, but automatic order submission is disabled.'],
    cta: 'START MANUAL',
  };
}

export const StrategyControlPanel: React.FC = () => {
  const strategies = useStrategyStore((s) => s.strategies);
  const { start, stop, setExecutionMode, setTradingMode, startAll, stopAll, getReadiness, refetchStrategies } = useStrategyControl();

  const [filter, setFilter] = useState<FilterKey>('ALL');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Strategy | null>(null);
  const [pendingStart, setPendingStart] = useState<Strategy | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [pendingStop, setPendingStop] = useState<Strategy | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return strategies.filter((s) => {
      if (filter !== 'ALL' && s.status !== filter) return false;
      if (search && !s.name.toLowerCase().includes(search.toLowerCase()) && !s.id.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [strategies, filter, search]);

  const summary = useMemo(() => ({
    total: strategies.length,
    running: strategies.filter((s) => s.status === 'RUNNING' || s.status === 'POSITION_ACTIVE').length,
    algo: strategies.filter((s) => s.executionMode === 'ALGO').length,
    paper: strategies.filter((s) => s.executionMode === 'PAPER').length,
    manual: strategies.filter((s) => s.tradingMode === 'MANUAL').length,
    positions: strategies.filter((s) => s.status === 'POSITION_ACTIVE').length,
    pnl: strategies.some((s) => s.pnl !== null)
      ? strategies.reduce((acc, s) => acc + (s.pnl || 0), 0)
      : null,
  }), [strategies]);

  const openStartConfirm = async (strategy: Strategy) => {
    setPendingStart(strategy);
    setReadiness(await getReadiness(strategy.id));
  };

  const confirmStart = async () => {
    if (!pendingStart) return;
    setBusy(pendingStart.id);
    const result = await start(pendingStart.id);
    setBusy(null);
    setPendingStart(null);
    setReadiness(null);
    if (!result.ok) window.alert(`Could not start ${pendingStart.name}: ${result.detail}`);
  };

  const confirmStop = async () => {
    if (!pendingStop) return;
    setBusy(pendingStop.id);
    await stop(pendingStop.id);
    setBusy(null);
    setPendingStop(null);
  };

  const pnl = formatPnl(summary.pnl);

  return (
    <div className="space-y-6">
      {/* SUMMARY CARDS — all values derived from live strategies[] (real backend state), never hardcoded */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-4">
        <MetricCard label="Total Strategies" value={summary.total} />
        <MetricCard label="Running" value={summary.running} subValueColor="bullish" />
        <MetricCard label="Algo Trade" value={summary.algo} subValueColor="bearish" />
        <MetricCard label="Paper Trade" value={summary.paper} subValueColor="neutral" />
        <MetricCard label="Manual Mode" value={summary.manual} subValueColor="muted" />
        <MetricCard label="Positions" value={summary.positions} subValueColor="bullish" />
        <MetricCard label="Today's P&L" value={pnl.text} subValueColor={pnl.color} />
      </div>

      {/* FILTER BAR */}
      <div className="flex flex-wrap items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg p-3">
        <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded p-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-colors ${
                filter === f ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {f.replace('_', ' ')}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-[160px] max-w-xs bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5">
          <Search size={12} className="text-zinc-500 shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search strategies..."
            aria-label="Search strategies"
            className="bg-transparent text-xs text-zinc-200 outline-none w-full placeholder:text-zinc-600"
          />
        </div>
        <button
          onClick={() => refetchStrategies()}
          title="Refresh"
          aria-label="Refresh strategy list"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-950 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors text-[10px] font-bold uppercase tracking-wider"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* STRATEGY TABLE */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <LayoutGrid size={18} className="text-sky-400" />
          <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Strategy Control</h3>
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 font-mono text-xs uppercase tracking-wider">
            {strategies.length === 0 ? 'NO DATA' : 'NO STRATEGIES MATCH FILTERS'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left whitespace-nowrap">
              <thead className="text-zinc-500 border-b border-zinc-800">
                <tr>
                  <th className="pb-2 font-normal uppercase pr-4">Strategy</th>
                  <th className="pb-2 font-normal uppercase pr-4">Status</th>
                  <th className="pb-2 font-normal uppercase pr-4">Start</th>
                  <th className="pb-2 font-normal uppercase pr-4">Trade Type</th>
                  <th className="pb-2 font-normal uppercase pr-4">Mode</th>
                  <th className="pb-2 font-normal uppercase pr-4">Signal</th>
                  <th className="pb-2 font-normal uppercase pr-4">Position</th>
                  <th className="pb-2 font-normal uppercase pr-4 text-right">Trades</th>
                  <th className="pb-2 font-normal uppercase pr-4 text-right">P&L</th>
                  <th className="pb-2 font-normal uppercase pr-4">Health</th>
                  <th className="pb-2 font-normal uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-850 text-zinc-300">
                {filtered.map((s) => {
                  const isRunning = s.status === 'RUNNING' || s.status === 'POSITION_ACTIVE' || s.status === 'SIGNAL';
                  const health = healthFromStatus(s.status, s.blockedReason);
                  const rowPnl = formatPnl(s.pnl);
                  return (
                    <tr key={s.id} className="hover:bg-zinc-800/30">
                      <td className="py-3 pr-4">
                        <button
                          onClick={() => setSelected(s)}
                          className="text-left text-zinc-100 font-sans font-semibold hover:text-sky-400 transition-colors"
                        >
                          {s.name}
                        </button>
                      </td>
                      <td className="py-3 pr-4"><StatusBadge status={s.status} /></td>
                      <td className="py-3 pr-4">
                        <button
                          disabled={busy === s.id}
                          aria-label={isRunning ? `Stop ${s.name}` : `Start ${s.name}`}
                          onClick={() => (isRunning ? setPendingStop(s) : openStartConfirm(s))}
                          className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border transition-colors disabled:opacity-40 ${
                            isRunning
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20'
                              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
                          }`}
                        >
                          {isRunning ? <Square size={10} /> : <Play size={10} />}
                          {isRunning ? 'ON' : 'OFF'}
                        </button>
                      </td>
                      <td className="py-3 pr-4">
                        <Segmented
                          value={s.executionMode}
                          disabled={isRunning}
                          onChange={(v) => setExecutionMode(s.id, v as ExecutionMode)}
                          options={[
                            { value: 'ALGO', label: 'Algo', color: 'rose' },
                            { value: 'PAPER', label: 'Paper', color: 'sky' },
                          ]}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <Segmented
                          value={s.tradingMode}
                          disabled={isRunning}
                          onChange={(v) => setTradingMode(s.id, v as TradingMode)}
                          options={[
                            { value: 'AUTO', label: 'Auto', color: 'sky' },
                            { value: 'MANUAL', label: 'Manual', color: 'amber' },
                          ]}
                        />
                      </td>
                      <td className="py-3 pr-4 text-zinc-300">{s.signal || '—'}</td>
                      <td className="py-3 pr-4">{s.status === 'POSITION_ACTIVE' ? <StatusBadge status="ACTIVE" /> : 'NONE'}</td>
                      <td className="py-3 pr-4 text-right tabular-nums">{s.tradeCount}</td>
                      <td className={`py-3 pr-4 text-right tabular-nums font-semibold ${
                        rowPnl.color === 'bullish' ? 'text-emerald-400' : rowPnl.color === 'bearish' ? 'text-rose-400' : 'text-zinc-500'
                      }`}>{rowPnl.text}</td>
                      <td className="py-3 pr-4">
                        <span title={s.blockedReason || undefined}>
                          <StatusBadge status={health.badge} />
                        </span>
                        <span className="ml-1.5 text-[10px] text-zinc-500 uppercase">{health.label}</span>
                      </td>
                      <td className="py-3">
                        <button
                          onClick={() => setSelected(s)}
                          aria-label={`Open ${s.name} configuration`}
                          className="text-zinc-500 hover:text-zinc-200 transition-colors"
                        >
                          <Settings2 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* QUICK ACTIONS */}
      <div className="flex flex-wrap gap-3 bg-zinc-900 border border-zinc-800 rounded-lg p-3">
        <button
          onClick={() => startAll()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors text-[10px] font-bold uppercase tracking-wider"
        >
          <Play size={12} /> Start All Strategies
        </button>
        <button
          onClick={() => stopAll()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rose-500/20 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-colors text-[10px] font-bold uppercase tracking-wider"
        >
          <Square size={12} /> Stop All Strategies
        </button>
        <button
          onClick={async () => {
            const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            await fetch(`${baseUrl}/api/v1/algo-config/disable`, { method: 'POST' });
            await refetchStrategies();
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors text-[10px] font-bold uppercase tracking-wider"
        >
          <PowerOff size={12} /> Disable All Algo Trading
        </button>
      </div>

      {/* START CONFIRMATION MODAL */}
      {pendingStart && (
        <div className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">
              {startConfirmCopy(pendingStart).title}
            </h4>
            <div className="space-y-1.5 text-xs font-mono text-zinc-400">
              {startConfirmCopy(pendingStart).lines.map((l, i) => <p key={i}>{l}</p>)}
            </div>
            {readiness && !readiness.all_passed && (
              <div className="bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2 space-y-1">
                {readiness.checks.filter((c) => !c.passed).map((c) => (
                  <p key={c.name} className="text-[11px] text-rose-400 font-mono">✗ {c.name}: {c.reason}</p>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => { setPendingStart(null); setReadiness(null); }}
                className="px-4 py-2 text-xs font-bold uppercase tracking-wider rounded-lg border border-zinc-700 text-zinc-400 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                onClick={confirmStart}
                disabled={busy === pendingStart.id}
                className="px-4 py-2 text-xs font-bold uppercase tracking-wider rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-50"
              >
                {startConfirmCopy(pendingStart).cta}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STOP CONFIRMATION MODAL */}
      {pendingStop && (
        <div className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">STOP {pendingStop.name}?</h4>
            <p className="text-xs font-mono text-zinc-400">New automated entries will be disabled.</p>
            <p className="text-xs font-mono text-zinc-400">Existing positions will remain under the existing position/risk management.</p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setPendingStop(null)}
                className="px-4 py-2 text-xs font-bold uppercase tracking-wider rounded-lg border border-zinc-700 text-zinc-400 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                onClick={confirmStop}
                disabled={busy === pendingStop.id}
                className="px-4 py-2 text-xs font-bold uppercase tracking-wider rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 disabled:opacity-50"
              >
                Stop Strategy
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DETAIL DRAWER — mirrors DetailDrawer.tsx's exact shell */}
      {selected && (
        <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-zinc-900 border-l border-zinc-800 shadow-none flex flex-col h-full animate-in slide-in-from-right duration-300">
          <div className="h-16 px-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/80">
            <div className="flex items-center gap-2.5">
              <LayoutGrid size={16} className="text-sky-400" />
              <span className="font-sans font-bold text-sm tracking-wider uppercase text-zinc-100">{selected.name}</span>
            </div>
            <button
              onClick={() => setSelected(null)}
              aria-label="Close strategy detail"
              className="p-1.5 hover:bg-zinc-850 rounded-lg text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="space-y-1">
              <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold font-sans">Description</p>
              <p className="text-sm text-zinc-300 font-sans">{selected.description || 'No description.'}</p>
            </div>

            <div className="pt-4 border-t border-zinc-850 space-y-3">
              <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold font-sans">Configuration</p>
              <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Status</span>
                  <StatusBadge status={selected.status} />
                </div>
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Execution Mode</span>
                  <span className="text-zinc-100">{selected.executionMode}</span>
                </div>
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Trading Mode</span>
                  <span className="text-zinc-100">{selected.tradingMode}</span>
                </div>
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Signal</span>
                  <span className="text-zinc-100">{selected.signal || '—'}</span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-zinc-850 space-y-3">
              <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold font-sans">Performance</p>
              <div className="grid grid-cols-3 gap-3 text-xs font-mono">
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Trades Today</span>
                  <span className="text-zinc-100 text-sm font-semibold">{selected.tradeCount}</span>
                </div>
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">Win Rate</span>
                  <span className="text-zinc-100 text-sm font-semibold">{selected.winRate || '—'}</span>
                </div>
                <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-850">
                  <span className="text-zinc-500 block mb-1">P&L</span>
                  <span className={`text-sm font-semibold ${formatPnl(selected.pnl).color === 'bullish' ? 'text-emerald-400' : formatPnl(selected.pnl).color === 'bearish' ? 'text-rose-400' : 'text-zinc-500'}`}>
                    {formatPnl(selected.pnl).text}
                  </span>
                </div>
              </div>
            </div>

            {selected.blockedReason && (
              <div className="pt-4 border-t border-zinc-850 space-y-2">
                <p className="text-[10px] text-rose-400 uppercase tracking-widest font-bold font-sans">Blocked Reason</p>
                <p className="text-xs font-mono text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">{selected.blockedReason}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategyControlPanel;
