import React from 'react';
import MetricCard from '../components/MetricCard';
import PositionPanel from '../components/PositionPanel';

const PnlView: React.FC = () => {
  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Workstation Compiled P&L tracking</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Dynamic mark-to-market returns ledger.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard label="Realized MTM" value="+₹18,450" subValueColor="bullish" />
        <MetricCard label="Unrealized MTM" value="+₹4,852.50" subValueColor="bullish" />
        <MetricCard label="Total Charges" value="₹340.00" subValueColor="bearish" />
        <MetricCard label="Net Return %" value="+4.85%" subValueColor="bullish" />
      </div>

      <PositionPanel />
    </div>
  );
};

export default PnlView;
