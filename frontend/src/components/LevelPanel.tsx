import React, { useState } from 'react';
import ChartPanel from './ChartPanel';

export const LevelPanel: React.FC = () => {
  const [showFib, setShowFib] = useState(false);
  const [showCPR, setShowCPR] = useState(true);

  const priceData = [
    { time: '2026-08-11', value: 24410 },
    { time: '2026-08-12', value: 24450 },
    { time: '2026-08-13', value: 24430 },
    { time: '2026-08-14', value: 24480 },
    { time: '2026-08-15', value: 24510 },
    { time: '2026-08-16', value: 24495 },
    { time: '2026-08-17', value: 24500 },
  ];

  const toggleFib = () => setShowFib(!showFib);
  const toggleCPR = () => setShowCPR(!showCPR);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Market Levels & Pivot Points
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">High-probability intraday levels & pivots visibility</p>
        </div>

        {/* Pivot Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleCPR}
            className={`px-3 py-1.5 rounded-lg text-xs font-sans tracking-wide transition-colors border ${
              showCPR
                ? 'bg-zinc-800 border-zinc-700 text-zinc-100 font-semibold'
                : 'bg-zinc-900 border-zinc-850 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Central Pivot Range (CPR)
          </button>
          <button
            onClick={toggleFib}
            className={`px-3 py-1.5 rounded-lg text-xs font-sans tracking-wide transition-colors border ${
              showFib
                ? 'bg-zinc-800 border-zinc-700 text-zinc-100 font-semibold'
                : 'bg-zinc-900 border-zinc-850 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Fibonacci Retracements
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 select-none">
        {/* Core Levels Table */}
        <div className="lg:col-span-1 bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <h4 className="text-zinc-100 font-sans text-xs font-bold uppercase tracking-wider">Default Pivots</h4>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-zinc-800/60 pb-2">
              <span className="text-rose-400">R2 Resistance</span>
              <span className="text-zinc-100 font-semibold">24,600</span>
            </div>
            <div className="flex justify-between border-b border-zinc-800/60 pb-2">
              <span className="text-rose-300">R1 Resistance</span>
              <span className="text-zinc-100 font-semibold">24,550</span>
            </div>
            <div className="flex justify-between border-b border-zinc-800/60 pb-2">
              <span className="text-sky-400">VWAP</span>
              <span className="text-zinc-100 font-semibold">24,460.50</span>
            </div>
            <div className="flex justify-between border-b border-zinc-800/60 pb-2">
              <span className="text-emerald-300">S1 Support</span>
              <span className="text-zinc-100 font-semibold">24,400</span>
            </div>
            <div className="flex justify-between pb-1">
              <span className="text-emerald-400">S2 Support</span>
              <span className="text-zinc-100 font-semibold">24,350</span>
            </div>
          </div>

          {/* CPR section */}
          {showCPR && (
            <div className="pt-4 border-t border-zinc-800 space-y-3">
              <h4 className="text-zinc-400 font-sans text-xs font-bold uppercase tracking-wider">Central Pivot Range</h4>
              <div className="space-y-2 text-xs font-mono text-zinc-300">
                <div className="flex justify-between">
                  <span>Top Central (TC):</span>
                  <span>24,455.00</span>
                </div>
                <div className="flex justify-between">
                  <span>Pivot Point (P):</span>
                  <span>24,450.00</span>
                </div>
                <div className="flex justify-between">
                  <span>Bottom Central (BC):</span>
                  <span>24,445.00</span>
                </div>
              </div>
            </div>
          )}

          {/* Fibonacci segment */}
          {showFib && (
            <div className="pt-4 border-t border-zinc-800 space-y-3">
              <h4 className="text-amber-400 font-sans text-xs font-bold uppercase tracking-wider">Fibonacci Extensions</h4>
              <div className="space-y-2 text-xs font-mono text-zinc-300">
                <div className="flex justify-between">
                  <span>61.8% Extension:</span>
                  <span>24,535.50</span>
                </div>
                <div className="flex justify-between">
                  <span>100% Extension:</span>
                  <span>24,610.00</span>
                </div>
                <div className="flex justify-between">
                  <span>161.8% Extension:</span>
                  <span>24,730.00</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Price Chart */}
        <div className="lg:col-span-2">
          <ChartPanel title="NIFTY Price Chart" data={priceData} showOverlays={{ vwap: true, support: true, resistance: true, cpr: showCPR }} />
        </div>
      </div>
    </div>
  );
};

export default LevelPanel;
