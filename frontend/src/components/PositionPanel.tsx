import React from 'react';
import { useLivePositions } from '../hooks/useLivePositions';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { LivePosition } from '../types/live';

export const PositionPanel: React.FC = () => {
  const { positions, loading, error, refetch } = useLivePositions();

  const columns: Column<LivePosition>[] = [
    {
      header: 'Instrument',
      accessor: (item) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Source',
      accessor: (item) => <StatusBadge status={item.source} />,
      align: 'center',
    },
    {
      header: 'Qty',
      accessor: (item) => <span className="font-mono text-zinc-300 tabular-nums">{item.quantity}</span>,
      align: 'right',
    },
    {
      header: 'Entry Price',
      accessor: (item) => <span className="font-mono text-zinc-200 tabular-nums">₹{item.entryPrice.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: LivePosition) => (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 select-none p-2 text-xs">
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Created</p>
        <p className="font-mono text-sm text-zinc-200 mt-1">{item.createdAt}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Closed</p>
        <p className="font-mono text-sm text-zinc-200 mt-1">{item.closedAt ?? '—'}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Exit Reason</p>
        <p className="text-zinc-300 mt-1">{item.exitReason ?? '—'}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Option Type</p>
        <p className="text-zinc-300 mt-1">{item.optionType}</p>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Open Positions Monitor
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real positions from Manual Trading and CAS Dislocation</p>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-sans bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {!error && positions.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No positions.
        </div>
      )}

      {positions.length > 0 && (
        <FoldableDataTable
          data={positions}
          columns={columns}
          rowKey={(item) => item.id}
          renderExpanded={renderExpanded}
        />
      )}
    </div>
  );
};

export default PositionPanel;
