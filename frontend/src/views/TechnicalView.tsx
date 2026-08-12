import React from 'react';

const TechnicalView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Technical Indicator Matrix</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Configurable indicator filters including EMA, SMA, VWAP, RSI, MACD, Bollinger Bands, ATR and Supertrend.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {[
          { name: 'Exponential Moving Average (EMA)', value: '24,482.10', status: 'Above (Bullish)', valColor: 'text-emerald-400' },
          { name: 'Relative Strength Index (RSI)', value: '62.40', status: 'Moderate (Neutral)', valColor: 'text-zinc-200' },
          { name: 'MACD Hist', value: '+14.50', status: 'Bullish Crossover', valColor: 'text-emerald-400' },
          { name: 'Average True Range (ATR)', value: '185.20', status: 'High Volatility', valColor: 'text-rose-400' },
          { name: 'Supertrend (7, 3)', value: '24,390.00', status: 'BUY Triggered', valColor: 'text-emerald-400' },
          { name: 'Bollinger Bands (20, 2)', value: '24,510 - 24,390', status: 'Nearing Upper Dev', valColor: 'text-zinc-200' },
        ].map((ind, idx) => (
          <div key={idx} className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-3 font-mono text-xs">
            <p className="font-sans font-semibold text-zinc-400">{ind.name}</p>
            <p className={`text-xl font-bold ${ind.valColor}`}>{ind.value}</p>
            <div className="flex justify-between text-[11px] text-zinc-500">
              <span>STATE ASSESSMENT:</span>
              <span className="font-sans font-bold uppercase">{ind.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TechnicalView;
