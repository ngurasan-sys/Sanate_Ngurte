import React, { useEffect, useState } from 'react';

// Interfaces based on the JSON payload structure from backend
interface MarketBreadthData {
  index: string;
  sufficient_data: boolean;
  reason?: string;
  advance_decline?: {
    adv: number;
    dec: number;
  };
  macro_trend?: {
    status: string;
    last_3_days: string[];
  };
}

export const MarketBreadthPage: React.FC = () => {
  const [data, setData] = useState<MarketBreadthData | null>(null);

  useEffect(() => {
    // Attempt WebSocket connection for live breadth data
    const wsUrl = `ws://localhost:8000/ws/market_breadth`;
    let ws: WebSocket | null = null;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Connected to market_breadth WS');
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setData(parsed);
        } catch (e) {
          console.error("Failed to parse market breadth message", e);
        }
      };

      ws.onclose = () => {
        console.log('market_breadth WS closed');
      };
    } catch (e) {
      console.error("WebSocket init error", e);
    }

    return () => {
      if (ws) ws.close();
    };
  }, []);

  if (!data || !data.sufficient_data) {
    return (
      <div className="bg-[#0f172a] min-h-screen text-zinc-100 p-8 flex items-center justify-center select-none">
        <div className="flex flex-col items-center gap-4 text-center max-w-md">
          <div className="w-8 h-8 border-4 border-zinc-700 border-t-zinc-400 rounded-full animate-spin"></div>
          <p className="text-zinc-400 font-sans">
            {data?.reason ?? 'Awaiting market breadth data...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#0f172a] min-h-screen text-zinc-100 p-8 flex flex-col gap-8 select-none">
      {/* Component 1: Macro Trend Banner */}
      <div className="bg-[#1e293b] rounded-2xl p-8 border border-zinc-800 flex flex-col items-center justify-center space-y-6 shadow-xl">
        <h2 className="text-zinc-400 font-sans font-bold text-sm uppercase tracking-widest">EOD Macro Regime</h2>
        <div className="text-5xl font-extrabold tracking-tight text-emerald-400 drop-shadow-md">
          {data.macro_trend?.status.replace(/_/g, ' ') || 'AWAITING REGIME SYNC...'}
        </div>

        {data.macro_trend?.last_3_days && (
          <div className="flex gap-4 mt-4">
            {data.macro_trend.last_3_days.map((day, idx) => {
              const isBull = day.includes('LONG_BUILDUP') || day.includes('SHORT_COVERING');
              const colorClass = isBull ? 'bg-emerald-900/50 text-emerald-300 border-emerald-800' : 'bg-rose-900/50 text-rose-300 border-rose-800';
              return (
                <React.Fragment key={idx}>
                  <div className={`px-4 py-2 rounded-full border text-xs font-bold tracking-wider uppercase ${colorClass}`}>
                    {day.replace(/_/g, ' ')}
                  </div>
                  {data.macro_trend?.last_3_days && idx < data.macro_trend.last_3_days.length - 1 && (
                    <div className="flex items-center text-zinc-600">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>

      {/* Advance/Decline */}
      <div className="flex justify-end mb-2">
         <div className="text-2xl font-sans text-zinc-300 font-bold tracking-wide">
           <span className="text-emerald-400">Adv: {data.advance_decline?.adv ?? '-'}</span> <span className="mx-3 text-zinc-600">|</span> <span className="text-rose-400">Dec: {data.advance_decline?.dec ?? '-'}</span>
         </div>
      </div>
    </div>
  );
};

export default MarketBreadthPage;
