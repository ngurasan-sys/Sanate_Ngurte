import React from 'react';
import { usePortfolioStore } from '../stores/portfolioStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { Position } from '../mock/interfaces';

export const PositionPanel: React.FC = () => {
  const { positions } = usePortfolioStore();

  const columns: Column<Position>[] = [
    {
      header: 'Instrument',
      accessor: (item: Position) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Qty',
      accessor: (item: Position) => <span className="font-mono text-zinc-300 tabular-nums">{item.qty}</span>,
      align: 'right',
    },
    {
      header: 'LTP',
      accessor: (item: Position) => <span className="font-mono text-zinc-200 tabular-nums">₹{item.ltp.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'P&L',
      accessor: (item: Position) => (
        <span className={`font-mono font-bold tabular-nums ${item.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {item.pnl >= 0 ? '+' : ''}₹{item.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </span>
      ),
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item: Position) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: Position) => {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-6 select-none p-2 text-xs">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Entry Price</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">₹{item.entry.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Avg Price</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">₹{item.avgPrice.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Stop Loss</p>
          <p className="font-mono text-sm text-rose-400 mt-1">₹{item.stopLoss.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Target</p>
          <p className="font-mono text-sm text-emerald-400 mt-1">₹{item.target.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Greeks (Δ / Γ / Θ)</p>
          <p className="font-mono text-sm text-zinc-200 mt-1">
            {item.delta.toFixed(2)} / {item.gamma.toFixed(4)} / {item.theta.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Strategy Source</p>
          <p className="text-zinc-300 font-semibold mt-1">{item.strategy}</p>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
          Open Positions Monitor
        </h3>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real-time valuation, mark-to-market margins and risk thresholds</p>
      </div>

      <FoldableDataTable
        data={positions}
        columns={columns}
        rowKey={(item) => item.id}
        renderExpanded={renderExpanded}
      />
    </div>
  );
};

export default PositionPanel;
