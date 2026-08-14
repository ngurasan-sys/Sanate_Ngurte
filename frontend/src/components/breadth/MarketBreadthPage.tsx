import React, { useEffect, useState } from 'react';

// Interfaces based on the JSON payload structure from backend
interface MarketBreadthData {
  index: string;
  advance_decline: {
    adv: number;
    dec: number;
  };
  heavyweight_sync: Record<string, { status: string; oi_chg: string }>;
  macro_trend: {
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

  return (
    <div className="bg-[#0f172a] min-h-screen text-zinc-100 p-8 flex flex-col gap-8 select-none">
      {/* Component 1: Macro Trend Banner */}
      <div className="bg-[#1e293b] rounded-2xl p-8 border border-zinc-800 flex flex-col items-center justify-center space-y-6 shadow-xl">
        <h2 className="text-zinc-400 font-sans font-bold text-sm uppercase tracking-widest">EOD Macro Regime</h2>
        <div className="text-5xl font-extrabold tracking-tight text-emerald-400 drop-shadow-md">
          {data?.macro_trend.status.replace(/_/g, ' ') || 'AWAITING REGIME SYNC...'}
        </div>

        {data?.macro_trend.last_3_days && (
          <div className="flex gap-4 mt-4">
            {data.macro_trend.last_3_days.map((day, idx) => {
              const isBull = day.includes('LONG_BUILDUP') || day.includes('SHORT_COVERING');
              const colorClass = isBull ? 'bg-emerald-900/50 text-emerald-300 border-emerald-800' : 'bg-rose-900/50 text-rose-300 border-rose-800';
              return (
                <React.Fragment key={idx}>
                  <div className={`px-4 py-2 rounded-full border text-xs font-bold tracking-wider uppercase ${colorClass}`}>
                    {day.replace(/_/g, ' ')}
                  </div>
                  {idx < data.macro_trend.last_3_days.length - 1 && (
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

      {/* Middle Row: Adv/Dec and Heatmap */}
      <div className="flex flex-col gap-4">
        {/* Advance/Decline Simple Display */}
        <div className="flex justify-end mb-2">
           <div className="text-2xl font-sans text-zinc-300 font-bold tracking-wide">
             <span className="text-emerald-400">Adv: {data?.advance_decline.adv || '-'}</span> <span className="mx-3 text-zinc-600">|</span> <span className="text-rose-400">Dec: {data?.advance_decline.dec || '-'}</span>
           </div>
        </div>

        {/* Component 2: OI Buzz Heatmap */}
        <div className="bg-[#1e293b] rounded-2xl p-8 border border-zinc-800 shadow-xl">
           <h3 className="text-zinc-400 font-sans font-bold text-sm uppercase tracking-widest mb-6">Real-Time Sector OI Buzz</h3>
           <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
             {/* Mocking some other heatmap blocks to show the layout since prompt implies an overall heatmap grid */}
             {['RELIANCE', 'TCS', 'INFY', 'ITC', 'L&T', 'HINDUNILVR'].map(ticker => {
               // Just mocking colors for visual demonstration of the heatmap
               const isBull = ticker === 'RELIANCE' || ticker === 'L&T' || ticker === 'TCS';
               const blockColor = isBull ? 'bg-emerald-900/50 border-emerald-800' : 'bg-rose-900/50 border-rose-800';
               const statusText = isBull ? 'LONG BUILDUP' : 'SHORT BUILDUP';

               return (
                 <div key={ticker} className={`${blockColor} border rounded-xl p-4 flex flex-col justify-center items-center h-32 transition-transform hover:scale-105 cursor-default`}>
                   <span className="font-bold text-lg text-zinc-100 tracking-wide">{ticker}</span>
                   <span className="text-xs mt-2 font-medium tracking-wider text-zinc-300">{statusText}</span>
                 </div>
               )
             })}
           </div>
        </div>
      </div>

      {/* Component 3: Heavyweight Sync Tracker */}
      <div className="bg-[#1e293b] rounded-2xl p-8 border border-zinc-800 shadow-xl">
         <h3 className="text-zinc-400 font-sans font-bold text-sm uppercase tracking-widest mb-6">Heavyweight Sync Monitor (60m)</h3>

         {(() => {
            const hdfc = data?.heavyweight_sync['HDFCBANK'];
            const icici = data?.heavyweight_sync['ICICIBANK'];
            const inSync = hdfc && icici && hdfc.status === icici.status && hdfc.status.includes('BUILDUP');
            const syncClass = inSync ? 'ring-1 ring-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : '';

            return (
              <div className={`flex flex-row justify-between items-center gap-4 bg-[#0f172a] rounded-xl p-6 ${syncClass}`}>
                {data?.heavyweight_sync && Object.entries(data.heavyweight_sync).map(([ticker, info]) => {
                  const isBull = info.status.includes('LONG') || info.status.includes('COVERING');
                  const textColor = isBull ? 'text-emerald-400' : 'text-rose-400';

                  return (
                    <div key={ticker} className="flex flex-col items-center">
                      <span className="font-bold text-zinc-200 tracking-wider mb-1">{ticker}</span>
                      <span className={`text-xs font-mono font-medium ${textColor}`}>
                        {info.status.replace(/_/g, ' ')}
                      </span>
                    </div>
                  );
                })}
                {!data && <div className="text-zinc-500 mx-auto">Waiting for sync data...</div>}
              </div>
            );
         })()}
      </div>
    </div>
  );
};

export default MarketBreadthPage;
