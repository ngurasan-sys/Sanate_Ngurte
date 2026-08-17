import React from 'react';
import { useStrategyStore } from '../stores/strategyStore';
import type { Strategy } from '../stores/strategyStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';

export const StrategyPanel: React.FC = () => {
  const { strategies } = useStrategyStore();

  const columns: Column<Strategy>[] = [
    {
      header: 'Strategy Name',
      accessor: (item: Strategy) => <span className="font-semibold text-zinc-100">{item.name}</span>,
    },
    {
      header: 'Signal Today',
      accessor: (item: Strategy) => <StatusBadge status={item.signal || 'NO SIGNAL'} />,
      align: 'center',
    },
    {
      header: 'Confidence',
      accessor: (item: Strategy) => (
        <span className="font-mono tabular-nums">{item.confidence !== null ? `${item.confidence}%` : '—'}</span>
      ),
      align: 'right',
    },
    {
      header: 'Strategy P&L',
      accessor: (item: Strategy) => {
        if (item.pnl === null) return <span className="font-mono text-zinc-500">—</span>;
        return (
          <span className={`font-mono tabular-nums font-semibold ${item.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {item.pnl >= 0 ? '+' : ''}{item.pnl.toFixed(2)}R
          </span>
        );
      },
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item: Strategy) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  // Only real, backend-provided fields — the old expanded panel assumed
  // parameters/indicators/levels/oi/historicalStats that GET
  // /api/v1/strategies never actually sends (a latent type mismatch that
  // TS silently allowed before strategyStore's type was corrected).
  const renderExpanded = (item: Strategy) => {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 select-none p-2 text-xs">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Description</p>
          <p className="mt-2 text-zinc-300 font-sans">{item.description || 'No description.'}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Execution / Trading Mode</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            <div className="flex justify-between"><span className="text-zinc-500">Execution:</span><span>{item.executionMode}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">Trading Mode:</span><span>{item.tradingMode}</span></div>
          </div>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Today's Trades</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            <div className="flex justify-between"><span className="text-zinc-500">Trade Count:</span><span>{item.tradeCount}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">Win Rate:</span><span>{item.winRate || '—'}</span></div>
          </div>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Readiness</p>
          <div className="mt-2 space-y-1 text-zinc-300 font-mono">
            <div className="flex justify-between"><span className="text-zinc-500">State:</span><span>{item.readiness}</span></div>
            {item.blockedReason && (
              <p className="text-[11px] text-rose-400 italic mt-1">{item.blockedReason}</p>
            )}
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
