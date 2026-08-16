import React, { useEffect, useRef, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { PlayCircle } from 'lucide-react';
import MetricCard from './MetricCard';
import StatusBadge from './StatusBadge';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Underlying = 'NIFTY' | 'SENSEX';
type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

interface StrategyOption {
  name: string;
  label: string;
  description: string;
  direction: 'shortonly' | 'longonly';
}

interface Trade {
  entry_time: string;
  exit_time: string;
  strike: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  exit_reason: string;
}

interface EquityPoint {
  timestamp: string;
  equity: number;
}

interface BacktestResult {
  underlying: string;
  date_from: string;
  date_to: string;
  initial_cash: number;
  final_equity: number;
  total_return_pct: number;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  win_rate_pct: number | null;
  total_trades: number;
  trades: Trade[];
  equity_curve: EquityPoint[];
}

interface BacktestJob {
  job_id: string;
  status: JobStatus;
  result: BacktestResult | null;
  error: string | null;
}

export const BacktestPanel: React.FC = () => {
  const [underlying, setUnderlying] = useState<Underlying>('NIFTY');
  const [dateFrom, setDateFrom] = useState('2024-10-01');
  const [dateTo, setDateTo] = useState('2025-03-31');
  const [strategy, setStrategy] = useState('SHORT_STRADDLE');
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [lots, setLots] = useState('1');
  const [stopLoss, setStopLoss] = useState('50');
  const [target, setTarget] = useState('30');

  const [job, setJob] = useState<BacktestJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch(`${baseUrl()}/api/v1/backtest/strategies`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body) => {
        if (Array.isArray(body)) setStrategies(body);
      })
      .catch((e) => console.error('Failed to fetch strategy list', e));
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const selectedStrategy = strategies.find((s) => s.name === strategy);

  const pollJob = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${baseUrl()}/api/v1/backtest/jobs/${jobId}`);
        const body: BacktestJob = await response.json();
        setJob(body);
        if (body.status === 'COMPLETED' || body.status === 'FAILED') {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // transient — keep polling, next tick will retry
      }
    }, 1500);
  };

  const handleRun = async () => {
    setError(null);
    const lotsNum = parseInt(lots, 10) || 1;
    const slNum = parseFloat(stopLoss);
    const tgtNum = parseFloat(target);

    if (!dateFrom || !dateTo) return setError('Both dates are required.');
    if (dateFrom > dateTo) return setError('Start date must be before end date.');
    if (isNaN(slNum) || isNaN(tgtNum)) return setError('Stop loss and target must be numbers.');

    setSubmitting(true);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          date_from: dateFrom,
          date_to: dateTo,
          strategy,
          lots: lotsNum,
          stop_loss_pct: slNum,
          target_pct: tgtNum,
        }),
      });
      const body: BacktestJob = await response.json();
      if (!response.ok) {
        setError((body as any).detail || 'Backtest request rejected.');
      } else {
        setJob(body);
        pollJob(body.job_id);
      }
    } catch {
      setError('Failed to reach the backend — is it running?');
    } finally {
      setSubmitting(false);
    }
  };

  const result = job?.result;
  const running = job && (job.status === 'PENDING' || job.status === 'RUNNING');
  const chartData = result?.equity_curve.map((p) => ({
    time: new Date(p.timestamp).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }),
    equity: p.equity,
  })) || [];

  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Quantitative Historical Backtest</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">
          Backtest a strategy against real NIFTY/SENSEX 1-minute option OI data.
        </p>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-7 gap-4">
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">Underlying</label>
            <select
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={underlying}
              onChange={(e) => setUnderlying(e.target.value as Underlying)}
            >
              <option value="NIFTY">NIFTY</option>
              <option value="SENSEX">SENSEX</option>
            </select>
          </div>
          <div className="space-y-1 col-span-2">
            <label className="text-xs text-zinc-500 uppercase font-bold">Strategy</label>
            <select
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>{s.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">From</label>
            <input
              type="date"
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">To</label>
            <input
              type="date"
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">Lots</label>
            <input
              type="number"
              min={1}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={lots}
              onChange={(e) => setLots(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">Stop Loss %</label>
            <input
              type="number"
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-zinc-500 uppercase font-bold">Target %</label>
            <input
              type="number"
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200 font-mono"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
          </div>
        </div>

        {selectedStrategy && (
          <div className="flex items-center gap-2 text-xs text-zinc-400 font-mono">
            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold font-sans tracking-wider border uppercase ${
              selectedStrategy.direction === 'longonly'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
            }`}>
              {selectedStrategy.direction === 'longonly' ? 'Buying' : 'Selling'}
            </span>
            <span>{selectedStrategy.description}</span>
          </div>
        )}

        <div className="flex items-center justify-between">
          <button
            onClick={handleRun}
            disabled={submitting || !!running}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 disabled:text-zinc-500 text-white text-xs font-bold uppercase tracking-wider px-4 py-2 rounded transition-colors"
          >
            <PlayCircle size={14} />
            {running ? 'Running…' : 'Run Backtest'}
          </button>
          {job && <StatusBadge status={job.status} />}
        </div>

        {error && <p className="text-xs text-rose-400 font-mono">{error}</p>}
        {job?.status === 'FAILED' && <p className="text-xs text-rose-400 font-mono">{job.error}</p>}
      </div>

      {result && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <MetricCard label="Total Return %" value={`${result.total_return_pct.toFixed(2)}%`} subValueColor={result.total_return_pct >= 0 ? 'bullish' : 'bearish'} />
            <MetricCard label="Sharpe Ratio" value={result.sharpe_ratio !== null ? result.sharpe_ratio.toFixed(2) : '—'} />
            <MetricCard label="Max Drawdown" value={result.max_drawdown_pct !== null ? `${result.max_drawdown_pct.toFixed(2)}%` : '—'} subValueColor="bearish" />
            <MetricCard label="Win Rate" value={result.win_rate_pct !== null ? `${result.win_rate_pct.toFixed(1)}%` : '—'} />
          </div>

          <div className="bg-amber-950/30 border border-amber-900/50 rounded-lg p-4 text-xs text-amber-300 font-mono leading-relaxed">
            Fills are simulated at the option's last-traded close price, not a real bid/ask — the underlying
            data has no order-book depth. Selling and buying back "at close" is optimistic by construction,
            so treat these numbers as an upper bound on what real execution could achieve, not a forecast.
          </div>

          <div className="h-64 w-full bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="time" stroke="#52525b" fontSize={10} tickMargin={10} minTickGap={40} />
                <YAxis stroke="#52525b" fontSize={10} tickFormatter={(val: number) => `₹${(val / 1000).toFixed(0)}K`} domain={['dataMin - 1000', 'dataMax + 1000']} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px' }}
                  itemStyle={{ fontSize: '12px' }}
                  labelStyle={{ color: '#a1a1aa', fontSize: '12px', marginBottom: '4px' }}
                  formatter={(value: any) => [`₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`, 'Equity']}
                />
                <Area type="monotone" dataKey="equity" stroke="#10b981" fillOpacity={1} fill="url(#colorEquity)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-200 font-sans font-bold text-xs uppercase tracking-wider">
              Trade Log ({result.total_trades} trades)
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono text-zinc-400">
                <thead>
                  <tr className="border-b border-zinc-850 text-zinc-500 uppercase text-[10px]">
                    <th className="text-left py-2 pr-4">Entry</th>
                    <th className="text-left py-2 pr-4">Exit</th>
                    <th className="text-right py-2 pr-4">Strike</th>
                    <th className="text-right py-2 pr-4">Entry Px</th>
                    <th className="text-right py-2 pr-4">Exit Px</th>
                    <th className="text-right py-2 pr-4">PnL</th>
                    <th className="text-left py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, idx) => (
                    <tr key={idx} className="border-b border-zinc-850/50">
                      <td className="py-1.5 pr-4">{new Date(t.entry_time).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                      <td className="py-1.5 pr-4">{new Date(t.exit_time).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                      <td className="py-1.5 pr-4 text-right">{t.strike}</td>
                      <td className="py-1.5 pr-4 text-right">{t.entry_price.toFixed(2)}</td>
                      <td className="py-1.5 pr-4 text-right">{t.exit_price.toFixed(2)}</td>
                      <td className={`py-1.5 pr-4 text-right font-semibold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toFixed(2)}
                      </td>
                      <td className="py-1.5">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default BacktestPanel;
