import React from 'react';
import { useOptionStore } from '../stores/optionStore';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import type { OptionStrike } from '../mock/interfaces';

export const OptionChainPanel: React.FC = () => {
  const { optionChains, selectedExpiry, setSelectedExpiry, strikeRange, setStrikeRange } = useOptionStore();
  const currentSymbol = 'NIFTY'; // can parameterize
  const chains = optionChains[currentSymbol] || [];

  // Find current active chain based on expiry (defaults to first)
  const activeChain = chains.find((c) => c.expiry === selectedExpiry) || chains[0];
  const strikes = activeChain ? activeChain.strikes : [];

  const columns: Column<OptionStrike>[] = [
    // CE Data
    {
      header: 'CE LTP',
      accessor: (item: OptionStrike) => <span className="font-mono text-emerald-400 tabular-nums">₹{item.ce.ltp.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'CE OI',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-400 tabular-nums">{item.ce.oi.toLocaleString()}</span>,
      align: 'right',
    },
    {
      header: 'CE IV %',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-500 tabular-nums">{item.ce.iv.toFixed(1)}%</span>,
      align: 'right',
    },
    {
      header: 'CE Delta',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-400 tabular-nums">{item.ce.delta.toFixed(2)}</span>,
      align: 'right',
    },

    // Center Strike info
    {
      header: 'Strike',
      accessor: (item: OptionStrike) => (
        <span className={`font-mono font-bold px-2 py-0.5 rounded ${item.atm ? 'bg-zinc-800 text-zinc-100 border border-zinc-700' : 'text-zinc-300'}`}>
          {item.strike} {item.atm && <span className="text-[9px] text-zinc-500 ml-1">ATM</span>}
        </span>
      ),
      align: 'center',
    },

    // PE Data
    {
      header: 'PE Delta',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-400 tabular-nums">{item.pe.delta.toFixed(2)}</span>,
      align: 'left',
    },
    {
      header: 'PE IV %',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-500 tabular-nums">{item.pe.iv.toFixed(1)}%</span>,
      align: 'left',
    },
    {
      header: 'PE OI',
      accessor: (item: OptionStrike) => <span className="font-mono text-zinc-400 tabular-nums">{item.pe.oi.toLocaleString()}</span>,
      align: 'left',
    },
    {
      header: 'PE LTP',
      accessor: (item: OptionStrike) => <span className="font-mono text-rose-400 tabular-nums">₹{item.pe.ltp.toFixed(2)}</span>,
      align: 'left',
    },
  ];

  const renderExpanded = (item: OptionStrike) => {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-xs select-none p-2">
        {/* CE detail */}
        <div className="space-y-2 border-r border-zinc-800 pr-4">
          <p className="font-bold text-zinc-400 uppercase tracking-wider text-[10px]">CE (Call Option) Greek Risk Matrix</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-zinc-500">Volume:</span>{' '}
              <span className="font-mono text-zinc-200">{item.ce.volume.toLocaleString()}</span>
            </div>
            <div>
              <span className="text-zinc-500">Gamma:</span>{' '}
              <span className="font-mono text-zinc-200">{item.ce.gamma.toFixed(5)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Theta:</span>{' '}
              <span className="font-mono text-zinc-200">{item.ce.theta.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Vega:</span>{' '}
              <span className="font-mono text-zinc-200">{item.ce.vega.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Bid / Ask:</span>{' '}
              <span className="font-mono text-emerald-400">{item.ce.bid.toFixed(2)}</span> /{' '}
              <span className="font-mono text-rose-400">{item.ce.ask.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* PE detail */}
        <div className="space-y-2 pl-4">
          <p className="font-bold text-zinc-400 uppercase tracking-wider text-[10px]">PE (Put Option) Greek Risk Matrix</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-zinc-500">Volume:</span>{' '}
              <span className="font-mono text-zinc-200">{item.pe.volume.toLocaleString()}</span>
            </div>
            <div>
              <span className="text-zinc-500">Gamma:</span>{' '}
              <span className="font-mono text-zinc-200">{item.pe.gamma.toFixed(5)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Theta:</span>{' '}
              <span className="font-mono text-zinc-200">{item.pe.theta.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Vega:</span>{' '}
              <span className="font-mono text-zinc-200">{item.pe.vega.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-zinc-500">Bid / Ask:</span>{' '}
              <span className="font-mono text-emerald-400">{item.pe.bid.toFixed(2)}</span> /{' '}
              <span className="font-mono text-rose-400">{item.pe.ask.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Option Chain ({currentSymbol})
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">Subtle ATM highlighting with multi-greek analytics</p>
        </div>

        {/* Control Bar */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Expiry Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 font-mono">EXPIRY</span>
            <select
              value={selectedExpiry}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 text-zinc-100 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-zinc-700 font-mono cursor-pointer"
            >
              <option value="2026-08-20">20-AUG-2026</option>
              <option value="2026-08-27">27-AUG-2026</option>
            </select>
          </div>

          {/* Strikes Range Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 font-mono">STRIKES</span>
            <select
              value={strikeRange}
              onChange={(e) => setStrikeRange(parseInt(e.target.value))}
              className="bg-zinc-900 border border-zinc-800 text-zinc-100 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-zinc-700 font-mono cursor-pointer"
            >
              <option value="5">5 Strikes</option>
              <option value="10">10 Strikes</option>
            </select>
          </div>
        </div>
      </div>

      <FoldableDataTable
        data={strikes.slice(0, strikeRange)}
        columns={columns}
        rowKey={(item) => item.strike.toString()}
        renderExpanded={renderExpanded}
      />
    </div>
  );
};

export default OptionChainPanel;
