import React from 'react';
import InteractiveChart from '../components/InteractiveChart';

const InteractiveChartView: React.FC = () => {
    return (
        <div className="space-y-6 select-none h-full flex flex-col pb-10">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">Advanced Interactive Charting</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time WebSocket tick integration, multi-pane Open Interest (OI) analysis, order-flow tints, and drawing tools.</p>
            </div>

            <InteractiveChart symbol="NIFTY" />
        </div>
    );
};

export default InteractiveChartView;
