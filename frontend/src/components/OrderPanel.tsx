// frontend/src/components/OrderPanel.tsx
import React from 'react';
import { useLiveOrders } from '../hooks/useLiveOrders';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { LiveOrder } from '../types/live';

export const OrderPanel: React.FC = () => {
  const { orders, loading, error, refetch } = useLiveOrders();

  const columns: Column<LiveOrder>[] = [
    {
      header: 'Time',
      accessor: (item) => <span className="font-mono text-zinc-400">{item.timestamp}</span>,
    },
    {
      header: 'Instrument',
      accessor: (item) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Action',
      accessor: (item) => <span className="font-mono text-zinc-300">{item.action}</span>,
    },
    {
      header: 'Status',
      accessor: (item) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Orders Execution Log
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real execution results, most recent first</p>
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

      {!error && orders.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No executions logged yet.
        </div>
      )}

      {orders.length > 0 && (
        <FoldableDataTable
          data={orders}
          columns={columns}
          rowKey={(item) => item.id}
        />
      )}
    </div>
  );
};

export default OrderPanel;
