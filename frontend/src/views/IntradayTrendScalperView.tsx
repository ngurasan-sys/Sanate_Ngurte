import React from 'react';
import { GitBranch, Zap, ArrowRight } from 'lucide-react';
import { useMarketStore } from '../stores/marketStore';
import { useAlgoStore } from '../stores/algoStore';
import InteractiveChart from '../components/InteractiveChart';

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  let colorClass = 'bg-zinc-800 text-zinc-400 border-zinc-700';
  if (
    status === 'BULLISH' ||
    status === 'FILLED' ||
    status === 'ACTIVE' ||
    status === 'CONNECTED' ||
    status === 'BULLISH_TREND_CONFIRMED' ||
    status.includes('ENTRY_TIER') ||
    status === 'TRAILING' ||
    status === 'PROFIT_PROTECTION' ||
    status === 'BREAK_EVEN'
  ) {
    colorClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  } else if (
    status === 'BEARISH' ||
    status === 'BLOCKED' ||
    status === 'EXHAUSTED' ||
    status === 'DAILY_LIMIT_REACHED' ||
    status === 'TIME_BLOCKED' ||
    status === 'INVALIDATED' ||
    status === 'EXITED' ||
    status === 'BEARISH_TREND_CONFIRMED'
  ) {
    colorClass = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
  } else if (status === 'WAITING' || status === 'DISCOVERY' || status === 'AWAITING_PULLBACK' || status === 'SCANNING' || status === 'IDLE' || status === 'WAITING_FOR_OPEN' || status === 'NO_TRADE_ZONE') {
    colorClass = 'bg-sky-500/10 text-sky-400 border-sky-500/20';
  }

  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border ${colorClass}`}>
      {status}
    </span>
  );
};

export const IntradayTrendScalperView: React.FC = () => {
  const { indices } = useMarketStore();
  const nifty = indices.NIFTY;
  const { signals } = useAlgoStore();

  // Find latest signal mapping to our payload (intraday_trend_scalper WS updates would populate signals or custom state)
  // Since we rely on standard stores, we look for a signal matching this strategy.
  // In a real scenario, the algoStore would listen to "intraday_trend_scalper" topic and store it.
  const latestSignal = signals.find(s => s.strategy === "intraday_trend_scalper") || {
    market_regime: "WAITING FOR MARKET DATA",
    daily_trades_count: 0,
    oi_difference: 0,
    execution_state: {
      status: "IDLE",
      avg_entry: 0.0,
      current_sl: 0.0,
      quantity: 0,
      next_action: "Awaiting data..."
    },
    timestamp: "--:--:--"
  } as any;

  // We map the payload directly if it exists, otherwise fallbacks
  const data = {
    underlying: 'NIFTY',
    ltp: nifty?.spot || 0,
    regime: latestSignal.market_regime || "WAITING FOR MARKET DATA",
    trades: latestSignal.daily_trades_count || 0,
    oiDifference: latestSignal.oi_difference || 0,
    state: latestSignal.execution_state?.status || "IDLE",
    avgEntry: latestSignal.execution_state?.avg_entry || 0.0,
    currentSl: latestSignal.execution_state?.current_sl || 0.0,
    quantity: latestSignal.execution_state?.quantity || 0,
    nextAction: latestSignal.execution_state?.next_action || "Awaiting data...",
    timestamp: latestSignal.timestamp || "--:--:--"
  };

  return (
    <div className="space-y-6 select-none max-w-7xl mx-auto pb-10 bg-[#0f172a] min-h-screen text-zinc-100 p-6">

      {/* HEADER */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-zinc-100 font-sans font-bold text-2xl uppercase tracking-wider flex items-center gap-2">
            <GitBranch className="text-sky-500" size={24} /> INTRADAY TREND SCALPER
          </h2>
          <p className="text-sm text-zinc-400 font-sans mt-1">Confirmed trend execution with tiered entries and dynamic trailing.</p>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold mb-1">Market Regime</div>
            <StatusBadge status={data.regime} />
          </div>
          <div className="text-right">
            <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold mb-1">Trades</div>
            <div className="text-lg font-mono font-bold text-zinc-200">{data.trades} / 3</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* EXECUTION TRACKER CARD */}
        <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-8 space-y-6 shadow-none">
          <div className="flex justify-between items-center border-b border-zinc-800 pb-4">
            <span className="text-sm font-bold uppercase tracking-widest text-zinc-400 flex items-center gap-2">
              <Zap size={16} className="text-amber-400" /> EXECUTION STATE
            </span>
            <span className="text-xs font-mono text-zinc-500">{data.timestamp}</span>
          </div>

          <div className="flex justify-between items-end">
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-widest mb-2 font-bold">Current Status</div>
              <div className="text-3xl font-bold font-mono tracking-wide text-zinc-100">
                {data.state.replace(/_/g, ' ')}
              </div>
            </div>

            <div className="text-right">
              <div className="text-xs text-zinc-500 uppercase tracking-widest mb-2 font-bold">OI Conviction</div>
              <div className={`text-xl font-mono font-bold ${data.oiDifference > 4000000 ? 'text-emerald-400' : (data.oiDifference < -4000000 ? 'text-rose-400' : 'text-zinc-400')}`}>
                {data.oiDifference.toLocaleString()}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-6 pt-6 border-t border-zinc-800/50">
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Avg Entry</div>
              <div className="text-xl font-mono text-zinc-200">₹{data.avgEntry.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Active Stop</div>
              <div className="text-xl font-mono text-rose-400">₹{data.currentSl.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Quantity</div>
              <div className="text-xl font-mono text-zinc-200">{data.quantity} Lots</div>
            </div>
          </div>

          <div className="pt-4">
            <div className="text-xs text-zinc-500 uppercase tracking-widest mb-2">Next Action</div>
            <div className="text-sm text-sky-400/90 font-mono bg-sky-950/20 p-3 rounded border border-sky-900/30">
              {data.nextAction}
            </div>
          </div>
        </div>

        {/* LADDER VISUAL */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col h-full shadow-none">
          <div className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-6 border-b border-zinc-800 pb-4">
            ENTRY LADDER
          </div>

          <div className="flex-1 flex flex-col justify-between space-y-4">
            {/* TIER 1 */}
            <div className={`p-4 rounded border ${data.quantity >= 2 ? 'bg-emerald-950/30 border-emerald-900/50' : 'bg-zinc-950/50 border-zinc-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className={`text-sm font-bold uppercase tracking-wider ${data.quantity >= 2 ? 'text-emerald-400' : 'text-zinc-500'}`}>Tier 1</span>
                <span className={`text-xs font-mono ${data.quantity >= 2 ? 'text-emerald-400/70' : 'text-zinc-600'}`}>2 LOTS</span>
              </div>
              <div className="text-xs font-mono text-zinc-500">VWAP Pullback</div>
            </div>

            <div className="flex justify-center text-zinc-700">
              <ArrowRight className="rotate-90" size={16} />
            </div>

            {/* TIER 2 */}
            <div className={`p-4 rounded border ${data.quantity >= 6 ? 'bg-emerald-950/30 border-emerald-900/50' : 'bg-zinc-950/50 border-zinc-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className={`text-sm font-bold uppercase tracking-wider ${data.quantity >= 6 ? 'text-emerald-400' : 'text-zinc-500'}`}>Tier 2</span>
                <span className={`text-xs font-mono ${data.quantity >= 6 ? 'text-emerald-400/70' : 'text-zinc-600'}`}>4 LOTS</span>
              </div>
              <div className="text-xs font-mono text-zinc-500">SuperTrend / Reversal</div>
            </div>

            <div className="flex justify-center text-zinc-700">
              <ArrowRight className="rotate-90" size={16} />
            </div>

            {/* TIER 3 */}
            <div className={`p-4 rounded border ${data.quantity >= 14 ? 'bg-emerald-950/30 border-emerald-900/50' : 'bg-zinc-950/50 border-zinc-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className={`text-sm font-bold uppercase tracking-wider ${data.quantity >= 14 ? 'text-emerald-400' : 'text-zinc-500'}`}>Tier 3</span>
                <span className={`text-xs font-mono ${data.quantity >= 14 ? 'text-emerald-400/70' : 'text-zinc-600'}`}>8 LOTS</span>
              </div>
              <div className="text-xs font-mono text-zinc-500">Day High/Low Swing</div>
            </div>
          </div>
        </div>

      </div>

      {/* CHART PLACEHOLDER */}
      <div className="h-[500px] bg-slate-900/30 rounded-2xl border border-slate-800 p-6 flex flex-col">
        <div className="flex justify-between items-center mb-4">
          <span className="text-sm font-bold uppercase tracking-widest text-zinc-400">MARKET STRUCTURE & EXECUTION CHART</span>
          <div className="flex gap-4 text-xs font-mono text-zinc-500">
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-sky-400"></div> VWAP</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-purple-400"></div> SuperTrend</span>
            <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-rose-400"></div> Stop Loss</span>
          </div>
        </div>

        <div className="flex-1 rounded flex items-center justify-center bg-zinc-950/30 relative overflow-hidden">
          <InteractiveChart />
        </div>
      </div>

    </div>
  );
};
