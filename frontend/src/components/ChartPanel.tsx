import React, { useEffect, useRef, useState } from 'react';
import { createChart, LineSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, LineWidth } from 'lightweight-charts';

interface ChartPanelProps {
  title: string;
  data: { time: string; value: number }[];
  showOverlays?: {
    vwap?: boolean;
    support?: boolean;
    resistance?: boolean;
    cpr?: boolean;
    oi?: boolean;
    volume?: boolean;
  };
}

export const ChartPanel: React.FC<ChartPanelProps> = ({
  title,
  data,
  showOverlays = { vwap: true, support: true, resistance: true },
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const [overlays, setOverlays] = useState(showOverlays);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Create lightweight-chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#18181b' }, // bg-zinc-900
        textColor: '#a1a1aa', // text-zinc-400
      },
      grid: {
        vertLines: { color: '#27272a' }, // border-zinc-800
        horzLines: { color: '#27272a' },
      },
      width: chartContainerRef.current.clientWidth || 600,
      height: 320,
    });

    const lineSeries = chart.addSeries(LineSeries, {
      color: '#10b981', // green-500
      lineWidth: 2 as LineWidth,
    });

    lineSeries.setData(data);
    chartRef.current = chart;
    lineSeriesRef.current = lineSeries;

    // Handle resizing
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data]);

  // Optional: Custom overlays drawing
  const baseValue = data.length > 0 ? data[data.length - 1].value : 24500;

  const toggleOverlay = (key: keyof typeof overlays) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col gap-4">
      {/* Chart Headers */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-semibold text-sm tracking-wider uppercase">
            {title}
          </h3>
          <p className="text-[11px] text-zinc-500 font-sans mt-0.5">Interactive live-tick chart panel</p>
        </div>

        {/* Overlay Filters */}
        <div className="flex flex-wrap gap-2">
          {Object.keys(overlays).map((key) => {
            const active = overlays[key as keyof typeof overlays];
            return (
              <button
                key={key}
                onClick={() => toggleOverlay(key as keyof typeof overlays)}
                className={`px-2 py-1 rounded text-[10px] font-mono tracking-wider transition-colors border uppercase ${
                  active
                    ? 'bg-zinc-800 border-zinc-700 text-zinc-100 font-medium'
                    : 'bg-zinc-900 border-zinc-850 text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {key}
              </button>
            );
          })}
        </div>
      </div>

      {/* Lightweight Chart canvas wrapper */}
      <div className="relative">
        <div ref={chartContainerRef} className="w-full h-80 rounded overflow-hidden" />

        {/* Custom mock overlay lines labels displayed inside chart panel */}
        <div className="absolute top-4 left-4 z-10 flex flex-col gap-1.5 pointer-events-none select-none">
          {overlays.vwap && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-sky-400 inline-block" />
              <span className="text-[10px] font-mono text-sky-400">VWAP: {(baseValue - 12).toFixed(2)}</span>
            </div>
          )}
          {overlays.support && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-emerald-500 inline-block" />
              <span className="text-[10px] font-mono text-emerald-400">SUPPORT: {(baseValue - 50).toFixed(0)}</span>
            </div>
          )}
          {overlays.resistance && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-rose-500 inline-block" />
              <span className="text-[10px] font-mono text-rose-400">RESIST: {(baseValue + 60).toFixed(0)}</span>
            </div>
          )}
          {overlays.cpr && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-amber-400 inline-block" />
              <span className="text-[10px] font-mono text-amber-400">CPR Central: {(baseValue - 5).toFixed(2)}</span>
            </div>
          )}
          {overlays.oi && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-purple-400 inline-block" />
              <span className="text-[10px] font-mono text-purple-400">OI Bullish Ratio: 1.14</span>
            </div>
          )}
          {overlays.volume && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-0.5 bg-teal-400 inline-block" />
              <span className="text-[10px] font-mono text-teal-400">VOL: 1.2M Contracts</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChartPanel;
