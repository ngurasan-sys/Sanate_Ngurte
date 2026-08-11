import React from 'react';
import { useUiStore } from '../stores/uiStore';
import { ChevronDown, ChevronUp } from 'lucide-react';

export interface Column<T> {
  header: string;
  accessor: (item: T) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

interface FoldableDataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  rowKey: (item: T) => string;
  renderExpanded?: (item: T) => React.ReactNode;
}

export function FoldableDataTable<T>({
  data,
  columns,
  rowKey,
  renderExpanded,
}: FoldableDataTableProps<T>) {
  const { expandedRows, toggleRowExpanded } = useUiStore();

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-zinc-800 rounded-lg bg-zinc-900">
        <span className="text-sm text-zinc-500 font-sans">No data available</span>
      </div>
    );
  }

  return (
    <div className="w-full">
      {/* Desktop view: Tabular */}
      <div className="hidden md:block overflow-x-auto border border-zinc-800 rounded-lg bg-zinc-900">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/80 text-[11px] tracking-wider text-zinc-500 font-bold uppercase select-none">
              {renderExpanded && <th className="w-10 px-4 py-3"></th>}
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  className={`px-4 py-3 font-sans ${
                    col.align === 'right'
                      ? 'text-right'
                      : col.align === 'center'
                      ? 'text-center'
                      : 'text-left'
                  } ${col.className || ''}`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {data.map((item) => {
              const key = rowKey(item);
              const isExpanded = !!expandedRows[key];

              return (
                <React.Fragment key={key}>
                  {/* Primary Row */}
                  <tr
                    onClick={() => renderExpanded && toggleRowExpanded(key)}
                    className={`group transition-colors duration-150 select-none ${
                      renderExpanded ? 'cursor-pointer hover:bg-zinc-800/40' : 'hover:bg-zinc-800/20'
                    }`}
                  >
                    {renderExpanded && (
                      <td className="px-4 py-4 text-center text-zinc-500">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </td>
                    )}
                    {columns.map((col, idx) => (
                      <td
                        key={idx}
                        className={`px-4 py-4 text-sm font-sans text-zinc-200 ${
                          col.align === 'right'
                            ? 'text-right'
                            : col.align === 'center'
                            ? 'text-center'
                            : 'text-left'
                        } ${col.className || ''}`}
                      >
                        {col.accessor(item)}
                      </td>
                    ))}
                  </tr>

                  {/* Expanded Row Details */}
                  {renderExpanded && isExpanded && (
                    <tr className="bg-zinc-950/40">
                      <td colSpan={columns.length + 1} className="p-0">
                        <div className="p-5 border-t border-b border-zinc-800/50 bg-zinc-950/20">
                          {renderExpanded(item)}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile view: Transform rows into Stacked Cards */}
      <div className="block md:hidden space-y-4">
        {data.map((item) => {
          const key = rowKey(item);
          const isExpanded = !!expandedRows[key];

          return (
            <div
              key={key}
              className="border border-zinc-800 rounded-lg bg-zinc-900 p-4 transition-colors duration-150"
            >
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => renderExpanded && toggleRowExpanded(key)}
              >
                {/* Mobile summary using the first 2 columns */}
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">
                    {columns[0].header}
                  </span>
                  <span className="text-sm font-medium text-zinc-100">
                    {columns[0].accessor(item)}
                  </span>
                </div>

                <div className="flex items-center gap-4">
                  <div className="flex flex-col items-end gap-1">
                    <span className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">
                      {columns[columns.length - 1].header}
                    </span>
                    <span className="text-sm font-semibold">
                      {columns[columns.length - 1].accessor(item)}
                    </span>
                  </div>
                  {renderExpanded && (
                    <div className="text-zinc-500">
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  )}
                </div>
              </div>

              {/* Mobile Expanded Segment */}
              {renderExpanded && isExpanded && (
                <div className="mt-4 pt-4 border-t border-zinc-800 space-y-3">
                  {columns.slice(1, -1).map((col, idx) => (
                    <div key={idx} className="flex justify-between text-xs">
                      <span className="text-zinc-500">{col.header}</span>
                      <span className="text-zinc-300 font-medium">{col.accessor(item)}</span>
                    </div>
                  ))}
                  <div className="pt-2">{renderExpanded(item)}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default FoldableDataTable;
