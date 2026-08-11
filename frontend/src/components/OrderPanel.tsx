import React from 'react';
import { usePortfolioStore } from '../stores/portfolioStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { Order } from '../mock/interfaces';

export const OrderPanel: React.FC = () => {
  const { orders } = usePortfolioStore();

  const columns: Column<Order>[] = [
    {
      header: 'Time',
      accessor: (item: Order) => <span className="font-mono text-zinc-400">{item.time}</span>,
    },
    {
      header: 'Instrument',
      accessor: (item: Order) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Side',
      accessor: (item: Order) => <StatusBadge status={item.side} />,
      align: 'center',
    },
    {
      header: 'Qty',
      accessor: (item: Order) => <span className="font-mono text-zinc-300 tabular-nums">{item.quantity}</span>,
      align: 'right',
    },
    {
      header: 'Price',
      accessor: (item: Order) => <span className="font-mono text-zinc-200 tabular-nums">₹{item.price.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item: Order) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: Order) => {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 select-none p-2 text-xs">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Broker Order ID</p>
          <p className="font-mono text-zinc-300 mt-1">{item.brokerOrderId}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Associated Strategy</p>
          <p className="text-zinc-200 font-semibold mt-1">{item.strategy}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Automated Decision Trace</p>
          <p className="text-zinc-300 mt-1">{item.decision}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Pre-Execution Risk Logs</p>
          <p className="text-emerald-400 mt-1">{item.risk}</p>
        </div>
        {item.executionDetails && (
          <div className="md:col-span-2 lg:col-span-4 border-t border-zinc-800 pt-3">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Execution Routing Details</p>
            <p className="text-zinc-400 italic font-mono mt-1">{item.executionDetails}</p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
          Orders Execution Logs
        </h3>
        <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Order routing trace logs and audit parameters</p>
      </div>

      <FoldableDataTable
        data={orders}
        columns={columns}
        rowKey={(item) => item.id}
        renderExpanded={renderExpanded}
      />
    </div>
  );
};

export default OrderPanel;
