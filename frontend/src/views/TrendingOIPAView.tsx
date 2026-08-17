import React from 'react';
import { Flame, ArrowRight, Zap } from 'lucide-react';
import { useMarketStore } from '../stores/marketStore';
import { useAlgoStore } from '../stores/algoStore';

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  let colorClass = 'bg-zinc-800 text-zinc-400 border-zinc-700';
  if (status === 'BULLISH' || status === 'FILLED' || status === 'ACTIVE' || status === 'CONNECTED') {
    colorClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  } else if (status === 'BEARISH' || status === 'BLOCKED' || status === 'EXHAUSTED' || status === 'YES') {
    colorClass = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
  } else if (status === 'WAITING' || status === 'DISCOVERY' || status === 'DUAL TIER') {
    colorClass = 'bg-sky-500/10 text-sky-400 border-sky-500/20';
  }

  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border ${colorClass}`}>
      {status}
    </span>
  );
};

export const TrendingOIPAView: React.FC = () => {
  const { indices } = useMarketStore();
  const nifty = indices.NIFTY;
  const { signals } = useAlgoStore();

  // Connect to the latest signal from our engine if it exists
  const latestSignal = signals.find(s => s.strategy === "trending_oi_price_action" || s.strategy === "Trending OI + Price Action");

  // Set fallback states since this strategy only populates these dynamically when it gets data
  const data = {
    underlying: 'NIFTY',
    ltp: nifty?.spot || 0,
    change: nifty?.change || 0,
    discovery: 'ACTIVE',
    oi: {
      diffOiPct: 0,
      callOiChange: 0,
      putOiChange: 0,
      netPcr: 0,
      strengthDots: 0,
      regime: 'NO TRADE'
    },
    priceAction: {
      ltp: nifty?.spot || 0,
      vwap: 0,
      supertrend: 0,
      distance: 0,
      convergence: 'NO'
    },
    range: {
      dailyAtr: 0,
      dayHigh: 0,
      dayLow: 0,
      intradayRange: 0,
      atrUsage: 0,
      status: 'NO DATA'
    },
    resistance: {
      swingHigh: 0,
      resistanceLevel: 0,
      rejections: 0,
      falseBreakout: 'NO',
      status: 'NO DATA'
    },
    entryMode: {
      mode: 'DUAL TIER',
      tier1: 2,
      tier2: 2
    },
    position: {
      active: !!latestSignal,
      direction: latestSignal?.direction === 'CALL' ? 'BUY CE' : 'BUY PE',
      strike: latestSignal?.strike || 'NO DATA',
      expiry: 'N/A',
      entry: parseFloat(latestSignal?.entry || "0"),
      avgEntry: parseFloat(latestSignal?.entry || "0"),
      ltp: 0,
      lots: 0,
      sl: parseFloat(latestSignal?.stopLoss || "0"),
      pnl: 0,
      tier1: latestSignal ? 'FILLED' : 'WAITING',
      tier2: 'WAITING'
    },
    signal: {
      action: latestSignal?.direction === 'CALL' ? 'BUY CE' : (latestSignal?.direction === 'PUT' ? 'BUY PE' : 'NONE'),
      price: parseFloat(latestSignal?.entry || "0"),
      lots: 0,
      stop: parseFloat(latestSignal?.stopLoss || "0"),
      reason: latestSignal?.reason || 'Awaiting Setup',
      timestamp: latestSignal?.timestamp || '--:--:--'
    }
  };

  return (
    <div className="space-y-6 select-none max-w-7xl mx-auto pb-10">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider flex items-center gap-2">
          <Flame className="text-amber-500" /> TRENDING OI + PRICE ACTION
        </h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">3-minute timeframe momentum option buying with indicator confluence.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

        {/* MARKET */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Market</span>
            <StatusBadge status={nifty ? 'ACTIVE' : 'NO DATA'} />
          </div>
          <div className="flex justify-between items-center text-sm font-mono">
            <span className="text-zinc-400">Underlying</span>
            <span className="text-zinc-100 font-bold">{data.underlying}</span>
          </div>
          <div className="flex justify-between items-center text-sm font-mono tabular-nums">
            <span className="text-zinc-400">Futures LTP</span>
            <span className="text-zinc-100">₹{data.ltp.toFixed(2)}</span>
          </div>
          <div className="flex justify-between items-center text-sm font-mono tabular-nums">
            <span className="text-zinc-400">Change</span>
            <span className={data.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {data.change >= 0 ? '+' : ''}{data.change.toFixed(2)}
            </span>
          </div>
        </div>

        {/* OPENING DISCOVERY */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Opening Discovery</span>
            <StatusBadge status={data.discovery} />
          </div>
          <div className="flex justify-center items-center h-16 text-sm font-mono tabular-nums">
            <span className="text-zinc-500 mr-3">09:15</span>
            <ArrowRight className="text-zinc-700 mx-2" size={16} />
            <span className="text-zinc-500 ml-3">09:45</span>
          </div>
        </div>

        {/* TRENDING OI */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Trending OI</span>
            <StatusBadge status={data.oi.regime} />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs font-mono tabular-nums">
            <div className="flex justify-between">
              <span className="text-zinc-500">Diff OI %</span>
              <span className={data.oi.diffOiPct >= 40 ? 'text-emerald-400' : (data.oi.diffOiPct <= -40 ? 'text-rose-400' : 'text-zinc-300')}>
                {data.oi.diffOiPct > 0 ? '+' : ''}{data.oi.diffOiPct}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Net PCR</span>
              <span className="text-zinc-300">{data.oi.netPcr}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Call OI Δ</span>
              <span className="text-rose-400">{data.oi.callOiChange.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Put OI Δ</span>
              <span className="text-emerald-400">{data.oi.putOiChange.toLocaleString()}</span>
            </div>
          </div>
          <div className="flex justify-between items-center text-xs font-mono mt-2 pt-2 border-t border-zinc-850/50">
            <span className="text-zinc-400">Strength Dots</span>
            <div className="flex gap-1">
              {[...Array(5)].map((_, i) => (
                <div key={i} className={`w-2 h-2 rounded-full ${i < data.oi.strengthDots ? 'bg-amber-400' : 'bg-zinc-800'}`} />
              ))}
            </div>
          </div>
        </div>

        {/* PRICE ACTION */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Price Action</span>
            <span className="text-[10px] text-zinc-600 font-mono">3M FUTURES</span>
          </div>
          <div className="space-y-2 text-xs font-mono tabular-nums">
            <div className="flex justify-between">
              <span className="text-zinc-500">LTP</span>
              <span className="text-zinc-100">₹{data.priceAction.ltp.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">VWAP</span>
              <span className="text-sky-400 font-medium">₹{data.priceAction.vwap.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">SuperTrend(10,2)</span>
              <span className="text-purple-400 font-medium">₹{data.priceAction.supertrend.toFixed(2)}</span>
            </div>
            <div className="flex justify-between pt-2 border-t border-zinc-850/50">
              <span className="text-zinc-500">Distance |ST-VWAP|</span>
              <span className="text-zinc-300">{data.priceAction.distance.toFixed(1)} pts</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Convergence</span>
              <StatusBadge status={data.priceAction.convergence} />
            </div>
          </div>
        </div>

        {/* RANGE */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Range</span>
            <StatusBadge status={data.range.status} />
          </div>
          <div className="space-y-2 text-xs font-mono tabular-nums">
            <div className="flex justify-between">
              <span className="text-zinc-500">Daily ATR(14)</span>
              <span className="text-zinc-300">{data.range.dailyAtr.toFixed(1)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Day High</span>
              <span className="text-emerald-400/70">{data.range.dayHigh.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Day Low</span>
              <span className="text-rose-400/70">{data.range.dayLow.toFixed(2)}</span>
            </div>
            <div className="flex justify-between pt-2 border-t border-zinc-850/50">
              <span className="text-zinc-500">Intraday Range</span>
              <span className="text-zinc-100 font-medium">{data.range.intradayRange.toFixed(1)} pts</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">ATR Usage</span>
              <span className={data.range.atrUsage >= 95 ? 'text-rose-400' : 'text-zinc-300'}>{data.range.atrUsage.toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* RESISTANCE */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Resistance</span>
            <StatusBadge status={data.resistance.status} />
          </div>
          <div className="space-y-2 text-xs font-mono tabular-nums">
            <div className="flex justify-between">
              <span className="text-zinc-500">Prev Swing High</span>
              <span className="text-zinc-300">₹{data.resistance.swingHigh.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Resistance Level</span>
              <span className="text-zinc-300">₹{data.resistance.resistanceLevel.toFixed(2)}</span>
            </div>
            <div className="flex justify-between pt-2 border-t border-zinc-850/50">
              <span className="text-zinc-500">Rejection Count</span>
              <span className={data.resistance.rejections >= 3 ? 'text-rose-400' : 'text-zinc-300'}>{data.resistance.rejections} / 3</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">False Breakout (Wick)</span>
              <StatusBadge status={data.resistance.falseBreakout} />
            </div>
          </div>
        </div>
      </div>

      {/* FULL WIDTH POSITION / ENTRY PANELS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ENTRY MODE & LATEST SIGNAL */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-6 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center border-b border-zinc-850 pb-2 mb-4">
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Entry Mode</span>
              <StatusBadge status={data.entryMode.mode} />
            </div>
            <div className="flex gap-4">
              <div className="flex-1 p-3 bg-zinc-950 border border-zinc-850 rounded text-center">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Tier 1</div>
                <div className="text-xl font-mono text-zinc-100">{data.entryMode.tier1} Lots</div>
              </div>
              <div className="flex-1 p-3 bg-zinc-950 border border-zinc-850 rounded text-center">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Tier 2</div>
                <div className="text-xl font-mono text-zinc-100">{data.entryMode.tier2} Lots</div>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3 text-zinc-100 font-bold uppercase text-xs tracking-wider">
              <Zap size={14} className="text-amber-400" /> Latest Signal
            </div>
            <div className="bg-zinc-950 border border-zinc-850 rounded p-3 text-xs font-mono">
              <div className="flex justify-between items-center mb-2 pb-2 border-b border-zinc-800/50">
                <span className="text-zinc-500">{data.signal.timestamp}</span>
                <span className={data.signal.action.includes('CE') ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>{data.signal.action}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center mt-2">
                <div>
                  <div className="text-[10px] text-zinc-600 uppercase">Price</div>
                  <div className="text-zinc-300">₹{data.signal.price.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-zinc-600 uppercase">Lots</div>
                  <div className="text-zinc-300">{data.signal.lots}</div>
                </div>
                <div>
                  <div className="text-[10px] text-zinc-600 uppercase">Stop Loss</div>
                  <div className="text-zinc-300">₹{data.signal.stop.toFixed(1)}</div>
                </div>
              </div>
              <div className="mt-3 pt-2 text-center border-t border-zinc-800/50 text-[10px] text-zinc-500 uppercase">
                {data.signal.reason}
              </div>
            </div>
          </div>
        </div>

        {/* POSITION */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex justify-between items-center border-b border-zinc-850 pb-2 mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Active Position</span>
            {data.position.active ? (
              <StatusBadge status={data.position.direction} />
            ) : (
              <span className="text-xs font-mono text-zinc-500">NO POSITION</span>
            )}
          </div>

          {data.position.active ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm font-mono pb-2 border-b border-zinc-850">
                <div className="flex items-center gap-2 text-zinc-100 font-bold">
                  {data.position.strike} {data.position.direction.split(' ')[1]}
                  <span className="text-xs text-zinc-500 font-normal">{data.position.expiry}</span>
                </div>
                <div className={data.position.pnl >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                  {data.position.pnl >= 0 ? '+' : ''}{data.position.pnl.toFixed(1)} pts
                </div>
              </div>

              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs font-mono tabular-nums">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Entry Price</span>
                  <span className="text-zinc-300">₹{data.position.entry.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Current LTP</span>
                  <span className="text-zinc-100 font-medium">₹{data.position.ltp.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Avg Entry</span>
                  <span className="text-zinc-300">₹{data.position.avgEntry.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Total Lots</span>
                  <span className="text-zinc-100">{data.position.lots}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Stop Loss</span>
                  <span className="text-rose-400">₹{data.position.sl.toFixed(2)}</span>
                </div>
              </div>

              <div className="pt-4 mt-2 border-t border-zinc-850">
                <div className="flex gap-4">
                  <div className="flex-1 flex justify-between items-center">
                    <span className="text-[10px] uppercase font-bold text-zinc-600">Tier 1</span>
                    <StatusBadge status={data.position.tier1} />
                  </div>
                  <div className="flex-1 flex justify-between items-center">
                    <span className="text-[10px] uppercase font-bold text-zinc-600">Tier 2</span>
                    <StatusBadge status={data.position.tier2} />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-48 flex items-center justify-center text-zinc-600 text-xs font-mono uppercase tracking-widest border border-dashed border-zinc-800 rounded">
              Awaiting Signal
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
