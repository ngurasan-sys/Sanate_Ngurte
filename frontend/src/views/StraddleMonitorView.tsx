import React, { useEffect, useRef } from 'react';
import { useStraddleStore } from '../stores/straddleStore';
import { createChart, LineSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export const StraddleMonitorView: React.FC = () => {
  const { connect, disconnect, state, history } = useStraddleStore();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<{
    premium: ISeriesApi<"Line"> | null;
    vwap: ISeriesApi<"Line"> | null;
    ema: ISeriesApi<"Line"> | null;
  }>({ premium: null, vwap: null, ema: null });

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#A1A1AA', // zinc-400
      },
      grid: {
        vertLines: { color: 'rgba(39, 39, 42, 0.4)' }, // zinc-800
        horzLines: { color: 'rgba(39, 39, 42, 0.4)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
      },
    });

    chartRef.current = chart;

    if (typeof (chart as any).addLineSeries === 'function') {
      seriesRef.current.premium = (chart as any).addLineSeries({
        color: '#E4E4E7',
        lineWidth: 2,
      });
      seriesRef.current.vwap = (chart as any).addLineSeries({
        color: '#38BDF8',
        lineWidth: 1,
        lineStyle: 1,
      });
      seriesRef.current.ema = (chart as any).addLineSeries({
        color: '#FBBF24',
        lineWidth: 1,
        lineStyle: 2,
      });
    } else if (typeof chart.addSeries === 'function') {
      // v5 API
      seriesRef.current.premium = chart.addSeries(LineSeries, {
        color: '#E4E4E7',
        lineWidth: 2,
      }) as unknown as ISeriesApi<"Line">;
      seriesRef.current.vwap = chart.addSeries(LineSeries, {
        color: '#38BDF8',
        lineWidth: 1,
        lineStyle: 1,
      }) as unknown as ISeriesApi<"Line">;
      seriesRef.current.ema = chart.addSeries(LineSeries, {
        color: '#FBBF24',
        lineWidth: 1,
        lineStyle: 2,
      }) as unknown as ISeriesApi<"Line">;
    }

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    // Initial size
    setTimeout(handleResize, 0);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current.premium || history.length === 0) return;

    // We need to map history to lightweight-charts format
    // For this example, we'll assume 'time' is HH:MM:SS and we create a fake date to parse
    const today = new Date().toISOString().split('T')[0];

    const formatData = (key: 'premium' | 'vwap' | 'ema_20') => {
      return history.map(h => {
        const timestamp = new Date(`${today}T${h.time}Z`).getTime() / 1000;
        return {
          time: timestamp as any,
          value: h[key]
        };
      }).filter(d => !isNaN(d.time) && !isNaN(d.value)); // Filter out invalid
    };

    seriesRef.current.premium.setData(formatData('premium'));
    seriesRef.current.vwap?.setData(formatData('vwap'));
    seriesRef.current.ema?.setData(formatData('ema_20'));

  }, [history]);


  // Derived UI classes
  const regimeClasses = {
    'NON_DIRECTIONAL_STRADDLE_SELL': 'bg-amber-950/30 border-amber-800 text-amber-500',
    'DIRECTIONAL_TRENDING': 'bg-slate-900 border-slate-700 text-slate-400',
    'NO_TRADE_ZONE': 'bg-zinc-900 border-zinc-800 text-zinc-400',
    'UNCERTAIN': 'bg-zinc-900 border-zinc-800 text-zinc-400',
  };

  const currentRegime = state?.market_regime || 'UNCERTAIN';
  const regimeBannerStyle = regimeClasses[currentRegime as keyof typeof regimeClasses] || regimeClasses['UNCERTAIN'];
  const bannerMessage = currentRegime === 'NON_DIRECTIONAL_STRADDLE_SELL'
    ? 'Non-Directional Regime Detected: OI is balanced. Monitoring Short Straddle setups.'
    : currentRegime === 'DIRECTIONAL_TRENDING'
    ? 'Directional Regime Detected: Switch to directional trend module.'
    : 'Awaiting Regime Confirmation...';

  const vwap = state?.straddle_data?.vwap || 0;
  const premium = state?.straddle_data?.current_premium || 0;

  // Color coding: Red if premium > VWAP (bad for short), Green if premium < VWAP (good for short)
  const isPremiumHigh = premium > vwap;
  const vwapColor = vwap > 0 ? (isPremiumHigh ? 'text-rose-500' : 'text-emerald-500') : 'text-zinc-500';

  const actionSignal = state?.straddle_data?.action || 'WAIT';
  const actionColor = actionSignal === 'HOLD_SHORT' ? 'bg-emerald-950/50 text-emerald-400 border-emerald-800' : 'bg-rose-950/50 text-rose-400 border-rose-800';

  return (
    <div className="p-8 space-y-8 select-none" data-testid="straddle-engine-page">

      {/* Component 1: Market Regime Banner */}
      <div className={`p-4 rounded-xl border ${regimeBannerStyle}`}>
        <h2 className="font-sans font-bold text-lg">{bannerMessage}</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-[600px]">
        {/* Component 2: The Straddle Monitor Card */}
        <div className="col-span-1 bg-zinc-900 border border-zinc-800 rounded-xl p-8 flex flex-col justify-between">
          <div>
            <h3 className="text-zinc-400 font-sans text-sm tracking-wider uppercase mb-1">ATM Strike</h3>
            <div className="text-3xl font-mono tabular-nums text-zinc-100">{state?.atm_strike || '---'}</div>
          </div>

          <div>
            <h3 className="text-zinc-400 font-sans text-sm tracking-wider uppercase mb-1">Combined Premium</h3>
            <div className="text-5xl font-mono tabular-nums text-zinc-100">{premium ? `₹${premium.toFixed(2)}` : '---'}</div>
          </div>

          <div>
            <h3 className="text-zinc-400 font-sans text-sm tracking-wider uppercase mb-1">Active VWAP (SL)</h3>
            <div className={`text-3xl font-mono tabular-nums ${vwapColor}`}>
              {vwap ? `₹${vwap.toFixed(2)}` : '---'}
            </div>
          </div>

          <div>
            <h3 className="text-zinc-400 font-sans text-sm tracking-wider uppercase mb-3">Execution Signal</h3>
            <div className={`inline-block px-4 py-2 rounded-full border font-bold ${actionColor}`}>
              {actionSignal.replace('_', ' ')}
            </div>
          </div>
        </div>

        {/* Component 3: Synthetic Premium Chart */}
        <div className="col-span-2 bg-slate-900/40 border border-zinc-800 rounded-xl p-6 flex flex-col">
          <div className="flex items-center gap-4 mb-4">
             <div className="flex items-center gap-2">
                 <div className="w-3 h-0.5 bg-zinc-200"></div>
                 <span className="text-zinc-400 text-xs">Premium</span>
             </div>
             <div className="flex items-center gap-2">
                 <div className="w-3 h-0.5 bg-sky-400 border-dashed border-t border-sky-400"></div>
                 <span className="text-zinc-400 text-xs">VWAP</span>
             </div>
             <div className="flex items-center gap-2">
                 <div className="w-3 h-0.5 bg-amber-400 border-dotted border-t border-amber-400"></div>
                 <span className="text-zinc-400 text-xs">20 EMA</span>
             </div>
          </div>
          <div ref={chartContainerRef} className="flex-1 w-full" />
        </div>
      </div>
    </div>
  );
};
