import React from 'react';
import { useOptionStore } from '../stores/optionStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { SpotTrendingOIItem } from '../mock/interfaces';

export const OIPanel: React.FC = () => {
  const { spotTrendingOI } = useOptionStore();
  const currentSymbol = 'NIFTY'; // can parameterize
  const data = spotTrendingOI[currentSymbol] || [];

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
          {item.differenceOi.toLocaleString()}
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
          <p className="font-mono text-sm text-zinc-200 mt-1">{item.ceOi.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Put OI</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{item.peOi.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Change Call OI</p>
          <p className={`font-mono text-sm mt-1 ${item.changeCeOi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.changeCeOi >= 0 ? '+' : ''}
            {item.changeCeOi.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Change Put OI</p>
          <p className={`font-mono text-sm mt-1 ${item.changePeOi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.changePeOi >= 0 ? '+' : ''}
            {item.changePeOi.toLocaleString()}
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
      </div>

      <FoldableDataTable
        data={data}
        columns={columns}
        rowKey={(item) => item.time}
        renderExpanded={renderExpanded}
      />
    </div>
  );
};

export default OIPanel;
