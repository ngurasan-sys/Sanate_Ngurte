import React, { useEffect } from 'react';
import { useOptionStore } from '../stores/optionStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { SpotTrendingOIItem } from '../mock/interfaces';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, Line } from 'recharts';
import { formatIndianNumber } from '../utils/format';

export const OIPanel: React.FC = () => {
  const { spotTrendingOI, startWsLiveFeed, wsConnected } = useOptionStore();
  const [showGraph, setShowGraph] = React.useState(false);
  const currentSymbol = 'NIFTY'; // can parameterize
  const data = spotTrendingOI[currentSymbol] || [];

  useEffect(() => {
    startWsLiveFeed();
  }, [startWsLiveFeed]);

  const columns: Column<SpotTrendingOIItem>[] = [
    {
      header: 'Time',
      accessor: (item: SpotTrendingOIItem) => <span className="font-mono text-zinc-100">{item.time}</span>,
    },
    {
      header: 'Difference OI',
      accessor: (item: SpotTrendingOIItem) => (
        <span className={`font-mono tabular-nums ${item.differenceOi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.differenceOi >= 0 ? '+' : ''}
          {formatIndianNumber(item.differenceOi)}
        </span>
      ),
      align: 'right',
    },
    {
      header: 'Strength',
      accessor: (item: SpotTrendingOIItem) => <span className="font-mono tabular-nums">{item.strength}%</span>,
      align: 'right',
    },
    {
      header: 'Direction %',
      accessor: (item: SpotTrendingOIItem) => <span className="font-mono tabular-nums">{item.directionPercent}%</span>,
      align: 'right',
    },
    {
      header: 'Sentiment',
      accessor: (item: SpotTrendingOIItem) => <span className="text-xs font-semibold text-zinc-300">{item.sentiment}</span>,
    },
    {
      header: 'Direction',
      accessor: (item: SpotTrendingOIItem) => <StatusBadge status={item.direction} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: SpotTrendingOIItem) => {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 select-none">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Call OI</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{formatIndianNumber(item.ceOi)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Put OI</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{formatIndianNumber(item.peOi)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Change Call OI</p>
          <p className={`font-mono text-sm mt-1 ${item.changeCeOi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.changeCeOi >= 0 ? '+' : ''}
            {formatIndianNumber(item.changeCeOi)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Change Put OI</p>
          <p className={`font-mono text-sm mt-1 ${item.changePeOi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.changePeOi >= 0 ? '+' : ''}
            {formatIndianNumber(item.changePeOi)}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Spot Trending Open Interest (OI)
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real-time dynamic call/put difference calculations</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <input
              type="checkbox"
              className="rounded border-zinc-700 bg-zinc-900"
              checked={showGraph}
              onChange={(e) => setShowGraph(e.target.checked)}
            />
            Show Graph View
          </label>
          <div className="flex items-center gap-2 text-xs font-mono">
            Status: <span className={wsConnected ? "text-emerald-400" : "text-rose-400"}>{wsConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
          </div>
        </div>
      </div>

      {showGraph && data.length > 0 && (
        <div className="h-64 w-full bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={[...data].reverse()}>
              <defs>
                <linearGradient id="colorCall" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorPut" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="time" stroke="#52525b" fontSize={10} tickMargin={10} />
              <YAxis yAxisId="left" stroke="#52525b" fontSize={10} tickFormatter={(val: number) => (val/100000).toFixed(1) + 'L'} orientation="left" />
              <YAxis yAxisId="right" stroke="#52525b" fontSize={10} domain={['dataMin - 50', 'dataMax + 50']} orientation="right" />
              <Tooltip
                contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px' }}
                itemStyle={{ fontSize: '12px' }}
                labelStyle={{ color: '#a1a1aa', fontSize: '12px', marginBottom: '4px' }}
                formatter={(value: any, name: any) => {
                  const val = Number(value);
                  if (name === "Underlying LTP") return [val.toFixed(2), name];
                  return [formatIndianNumber(val), name];
                }}
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Area yAxisId="left" type="monotone" dataKey="changeCeOi" name="Call OI Chg" stroke="#f43f5e" fillOpacity={1} fill="url(#colorCall)" />
              <Area yAxisId="left" type="monotone" dataKey="changePeOi" name="Put OI Chg" stroke="#10b981" fillOpacity={1} fill="url(#colorPut)" />
              <Area yAxisId="left" type="step" dataKey="differenceOi" name="Diff OI" stroke="#3b82f6" fillOpacity={0} />
              <Line yAxisId="right" type="monotone" dataKey="ltp" name="Underlying LTP" stroke="#a1a1aa" dot={false} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.length === 0 ? (
        <div className="py-12 text-center text-zinc-500 font-mono text-sm border border-dashed border-zinc-800 rounded-lg">
          NO DATA
        </div>
      ) : (
        <FoldableDataTable
          data={data}
          columns={columns}
          rowKey={(item) => item.time}
          renderExpanded={renderExpanded}
        />
      )}
    </div>
  );
};

export default OIPanel;
