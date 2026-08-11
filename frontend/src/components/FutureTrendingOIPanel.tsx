import React from 'react';
import { useOptionStore } from '../stores/optionStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { FutureTrendingOIItem } from '../mock/interfaces';

export const FutureTrendingOIPanel: React.FC = () => {
  const { futureTrendingOI } = useOptionStore();
  const currentSymbol = 'NIFTY'; // can parameterize
  const data = futureTrendingOI[currentSymbol] || [];

  const columns: Column<FutureTrendingOIItem>[] = [
    {
      header: 'Time',
      accessor: (item: FutureTrendingOIItem) => <span className="font-mono text-zinc-100">{item.time}</span>,
    },
    {
      header: 'Future Price',
      accessor: (item: FutureTrendingOIItem) => <span className="font-mono tabular-nums text-zinc-100">₹{item.futurePrice.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'OI Change',
      accessor: (item: FutureTrendingOIItem) => (
        <span className={`font-mono tabular-nums ${item.oiChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.oiChange >= 0 ? '+' : ''}
          {item.oiChange.toLocaleString()}
        </span>
      ),
      align: 'right',
    },
    {
      header: 'OI Change %',
      accessor: (item: FutureTrendingOIItem) => (
        <span className={`font-mono tabular-nums ${item.oiChangePercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.oiChangePercent >= 0 ? '+' : ''}
          {item.oiChangePercent.toFixed(2)}%
        </span>
      ),
      align: 'right',
    },
    {
      header: 'Price Change',
      accessor: (item: FutureTrendingOIItem) => (
        <span className={`font-mono tabular-nums ${item.priceChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.priceChange >= 0 ? '+' : ''}
          {item.priceChange.toFixed(2)}
        </span>
      ),
      align: 'right',
    },
    {
      header: 'Classification',
      accessor: (item: FutureTrendingOIItem) => <StatusBadge status={item.classification} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: FutureTrendingOIItem) => {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 select-none">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Future OI</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{item.futureOi.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Volume</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{item.volume.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Basis</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">{item.basis.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Basis Change</p>
          <p className={`font-mono text-sm mt-1 ${item.basisChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.basisChange >= 0 ? '+' : ''}
            {item.basisChange.toFixed(2)}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
          Future Trending Open Interest (OI)
        </h3>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time dynamic future basis and OI builder classifications</p>
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

export default FutureTrendingOIPanel;
