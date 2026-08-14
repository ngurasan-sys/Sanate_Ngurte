import React from 'react';
import { useChopFilterStore } from '../stores/useChopFilterStore';
import { useChopFilterWebSocket } from '../hooks/useChopFilterWebSocket';
import { Coffee, TrendingUp, TrendingDown, AlertTriangle, Activity } from 'lucide-react';
import InteractiveChart from '../components/InteractiveChart';

export const PullbackChopFilterView: React.FC = () => {
  useChopFilterWebSocket();
  const state = useChopFilterStore();

  if (!state.timestamp || state.connectionStatus !== 'CONNECTED') {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full bg-[#0a0f1c] text-slate-400 gap-4 min-h-[600px]">
        <Activity className="animate-spin" size={32} />
        <p className="font-mono text-sm tracking-widest uppercase">Awaiting Market Data & Signal State...</p>
      </div>
    );
  }

  // Determine Banner Colors & Icon
  let bannerClass = "bg-slate-900/50 border-slate-700";
  let bannerTitle = "NO TRADE ZONE";
  let bannerDesc = "Price consolidated between VWAP and SuperTrend or low Conviction.";

  if (state.marketState === 'TRENDING_BULLISH') {
    bannerClass = "bg-emerald-950/40 border-emerald-800";
    bannerTitle = "BULLISH TREND CONFIRMED";
    bannerDesc = "Awaiting Pullback Setup.";
  } else if (state.marketState === 'TRENDING_BEARISH') {
    bannerClass = "bg-rose-950/40 border-rose-800";
    bannerTitle = "BEARISH TREND CONFIRMED";
    bannerDesc = "Awaiting Bearish Pullback Setup.";
  }

  const oiDivergenceColor = (state.oiData?.diffPct || 0) >= 45 ? "text-emerald-400" : (state.oiData?.diffPct || 0) <= -45 ? "text-rose-400" : "text-slate-400";

  let signalBg = "bg-slate-900/30";
  let signalText = "text-slate-400";
  let SignalIcon = Coffee;

  if (state.activeSignal?.type === "BUY_TIER_1") {
    signalBg = "bg-emerald-900/30";
    signalText = "text-emerald-400";
    SignalIcon = TrendingUp;
  } else if (state.activeSignal?.type === "BUY_TIER_2") {
     signalBg = "bg-emerald-800/40 border border-emerald-700/50";
     signalText = "text-emerald-300 font-bold";
     SignalIcon = TrendingUp;
  } else if (state.activeSignal?.type === "STOP_LOSS_HIT") {
    signalBg = "bg-rose-900/50 border border-rose-500";
    signalText = "text-rose-300";
    SignalIcon = AlertTriangle;
  } else if (state.activeSignal?.color === "rose" && state.activeSignal?.type === "BUY_TIER_1") {
     signalBg = "bg-rose-900/30";
     signalText = "text-rose-400";
     SignalIcon = TrendingDown;
  } else if (state.activeSignal?.color === "rose" && state.activeSignal?.type === "BUY_TIER_2") {
     signalBg = "bg-rose-800/40 border border-rose-700/50";
     signalText = "text-rose-300 font-bold";
     SignalIcon = TrendingDown;
  }

  return (
    <div className="flex flex-col p-6 gap-8 bg-[#0a0f1c] min-h-screen text-zinc-100">

      {/* Banner */}
      <div className={`w-full p-6 rounded-2xl border ${bannerClass} flex flex-col justify-center items-center text-center transition-colors duration-500`}>
        <h1 className="font-sans font-bold text-2xl tracking-widest mb-2">{bannerTitle}</h1>
        <p className="font-sans text-sm opacity-80">{bannerDesc}</p>
      </div>

      {/* Context & Signal Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

        {/* Left: Live Context */}
        <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-2xl flex flex-col gap-4">
          <h2 className="text-xs font-sans font-bold uppercase tracking-widest text-zinc-400 mb-2">Live Indicator Context</h2>

          <div className="grid grid-cols-2 gap-6">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Current LTP</span>
              <span className="font-mono tabular-nums text-2xl font-semibold">{state.priceData?.ltp.toFixed(2)}</span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">OI Divergence</span>
              <span className={`font-mono tabular-nums text-2xl font-semibold ${oiDivergenceColor}`}>
                {state.oiData?.diffPct.toFixed(1)}%
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">VWAP Level</span>
              <span className="font-mono tabular-nums text-xl">{state.priceData?.vwap.toFixed(2)}</span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">SuperTrend Level</span>
              <span className="font-mono tabular-nums text-xl">{state.priceData?.supertrend.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Right: Active Signal */}
        <div className={`p-6 rounded-2xl transition-colors duration-500 flex flex-col justify-center items-center text-center gap-4 ${signalBg}`}>
           <h2 className="text-xs font-sans font-bold uppercase tracking-widest opacity-60 mb-2">Active Signal</h2>

           <SignalIcon size={48} className={`opacity-80 ${signalText}`} />

           <div className={`text-xl font-bold tracking-wide ${signalText}`}>
             {state.activeSignal?.message || "Waiting for valid setup."}
           </div>

           {state.activeSignal?.type !== "WAIT" && (
             <div className="text-xs uppercase tracking-widest opacity-50 mt-2">
                STATE: {state.internalState}
             </div>
           )}
        </div>

      </div>

      {/* Chart Area */}
      <div className="h-[500px] w-full bg-slate-900/30 rounded-2xl border border-slate-800 p-4">
          {/* We reuse the InteractiveChart. Alternatively, we could create a specialized chart, but for this PR,
              we can use InteractiveChart to show NIFTY 3m which natively includes VWAP.
              Since the instruction says "If TradingView Lightweight Charts already exists: USE IT.",
              InteractiveChart fits perfectly. */}
          <InteractiveChart />
      </div>

    </div>
  );
};
