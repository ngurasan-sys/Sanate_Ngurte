import React from 'react';
import { useStrategyStore } from '../stores/strategyStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { Strategy } from '../mock/interfaces';

export const StrategyPanel: React.FC = () => {
  const { strategies } = useStrategyStore();

  const columns: Column<Strategy>[] = [
    {
      header: 'Strategy Name',
      accessor: (item: Strategy) => <span className="font-semibold text-zinc-100">{item.name}</span>,
    },
    {
      header: 'Signal Today',
      accessor: (item: Strategy) => <StatusBadge status={item.signal} />,
      align: 'center',
    },
    {
      header: 'Confidence',
      accessor: (item: Strategy) => <span className="font-mono tabular-nums">{item.confidence}%</span>,
      align: 'right',
    },
    {
      header: 'Strategy P&L',
      accessor: (item: Strategy) => (
        <span className={`font-mono tabular-nums font-semibold ${item.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.pnl >= 0 ? '+' : ''}₹{item.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </span>
      ),
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item: Strategy) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: Strategy) => {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 select-none p-2 text-xs">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Parameters</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            {Object.entries(item.parameters).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-zinc-500">{k}:</span>
                <span>{v.toString()}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Indicators Status</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            {Object.entries(item.indicators).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-zinc-500">{k}:</span>
                <span>{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Pivot Levels Target</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            <div className="flex justify-between">
              <span className="text-zinc-500">Supports:</span>
              <span>{item.levels.support.join(', ')}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Resistances:</span>
              <span>{item.levels.resistance.join(', ')}</span>
            </div>
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Historical Stats</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            <div className="flex justify-between">
              <span className="text-zinc-500">Win Rate:</span>
              <span className="text-emerald-400 font-bold">{item.historicalStats.winRate}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Total Trades:</span>
              <span>{item.historicalStats.totalTrades}</span>
            </div>
            <div className="mt-2 border-t border-zinc-800 pt-2">
              <p className="text-[9px] text-zinc-500 uppercase font-bold">OI Comment</p>
              <p className="text-[11px] text-zinc-300 italic truncate mt-1">{item.oi}</p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Active Algorithmic Strategies
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real-time status tracking, directional signals and historical win-rates</p>
        </div>
      </div>

      <FoldableDataTable
        data={strategies}
        columns={columns}
        rowKey={(item) => item.id}
        renderExpanded={renderExpanded}
      />
    </div>
  );
};

export default StrategyPanel;
