import React from 'react';
import StatusBadge from './StatusBadge';
import { useThreeMinuteGapStore } from '../stores/threeMinuteGapStore';
import { useThreeMinuteGapWebSocket } from '../hooks/useThreeMinuteGapWebSocket';

const ThreeMinuteGapPanel: React.FC = () => {
  const store = useThreeMinuteGapStore();

  // Wired to backend/app/strategies/three_minute_gap/engine.py's real FVG
  // detection + SuperTrend/OI confluence, broadcast on ws/three_minute_gap.
  useThreeMinuteGapWebSocket('NIFTY');

  return (
    <div className="space-y-6 select-none">
      <div>
        <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">3 Minute Gap</h2>
        <p className="text-xs text-zinc-400 font-sans mt-0.5">Automated trading model based on 3-minute Futures FVG discovery</p>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <div className="flex justify-between items-center">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Strategy Status</h4>
            <StatusBadge status={store.isConnected ? 'CONNECTED' : 'NO DATA'} />
          </div>
          <div className="grid grid-cols-3 gap-x-4 gap-y-2 font-mono text-xs text-zinc-400">
            <div className="flex justify-between border-b border-zinc-850 pb-1">
                <span>State:</span>
                <StatusBadge status={store.strategyStatus} />
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
                <span>Underlying:</span>
                <span className="text-zinc-100">{store.underlying}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-850 pb-1">
                <span>Execution:</span>
                <span className="text-amber-400 font-bold border border-amber-500/20 px-1 py-0.5 rounded">{store.executionMode}</span>
            </div>
          </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Futures Price Action */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Futures Price Action</h4>
            {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Futures LTP:</span>
                        <span className="text-zinc-100">₹{store.futuresPrice.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>3M Trend:</span>
                        <span>{store.threeMinTrend}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>SuperTrend:</span>
                        <span>{store.superTrend.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>VWAP:</span>
                        <span>{store.vwap.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Day High:</span>
                        <span>{store.dayHigh.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Day Low:</span>
                        <span>{store.dayLow.toFixed(2)}</span>
                    </div>
                </div>
            )}
        </div>

        {/* Gap Structure */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Gap Structure</h4>
            {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Type:</span>
                        <span className={store.gapType === 'BULLISH' ? 'text-emerald-400' : store.gapType === 'BEARISH' ? 'text-rose-400' : ''}>{store.gapType}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Base:</span>
                        <span>{store.gapBase.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Top:</span>
                        <span>{store.gapTop.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Size:</span>
                        <span>{Math.abs(store.gapTop - store.gapBase).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Status:</span>
                        <StatusBadge status={store.gapStatus} />
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Gap Age:</span>
                        <span>--</span>
                    </div>
                </div>
            )}
        </div>

        {/* Trending OI Confirmation */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Trending OI Confirmation</h4>
             {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Diff OI:</span>
                        <span>{store.diffOi.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Difference %:</span>
                        <span className={store.diffOiPercent >= 40 ? 'text-emerald-400' : store.diffOiPercent <= -40 ? 'text-rose-400' : ''}>
                            {store.diffOiPercent.toFixed(1)}%
                        </span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Strength Dots:</span>
                        <span>{store.strengthDots}/5</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Sentiment:</span>
                        <span className={store.sentiment === 'BULLISH' ? 'text-emerald-400' : store.sentiment === 'BEARISH' ? 'text-rose-400' : ''}>{store.sentiment}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Confirmation Status:</span>
                        <StatusBadge status={Math.abs(store.diffOiPercent) >= 40 && store.strengthDots >= 2 ? 'CONFIRMED' : 'WAITING'} />
                    </div>
                </div>
            )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Entry Structure */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Entry Structure</h4>
            {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Pullback Status:</span>
                        <span>{store.pullbackStatus}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>SuperTrend Interaction:</span>
                        <span>{store.superTrendInteraction}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>FVG Interaction:</span>
                        <span>{store.fvgInteraction}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Confirmation:</span>
                        <span>--</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Entry Status:</span>
                        <StatusBadge status={store.entryStatus} />
                    </div>
                </div>
            )}
        </div>

        {/* Position */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Position</h4>
             {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Lots:</span>
                        <span className="text-zinc-100">{store.lots}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Entry Price:</span>
                        <span>₹{store.entryPrice.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Average Price:</span>
                        <span>₹{store.avgPrice.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Stop Loss:</span>
                        <span className="text-rose-400">₹{store.stopLoss.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Unrealized P&L:</span>
                        <span className={store.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>₹{store.unrealizedPnl.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Tier 2:</span>
                        <span className="text-zinc-500">DISABLED</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Tier 3:</span>
                        <span className="text-zinc-500">DISABLED</span>
                    </div>
                </div>
            )}
        </div>

        {/* Signal */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Signal</h4>
             {store.strategyStatus === 'NO DATA' ? (
                 <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">NO DATA</div>
            ) : (
                <div className="grid grid-cols-1 gap-y-2 font-mono text-xs text-zinc-400">
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Action:</span>
                        <span className={store.signalAction.includes('BUY') ? 'text-emerald-400 font-bold' : store.signalAction.includes('EXIT') ? 'text-rose-400 font-bold' : ''}>{store.signalAction}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Reason:</span>
                        <span>{store.signalReason}</span>
                    </div>
                    <div className="flex justify-between border-b border-zinc-850 pb-1">
                        <span>Timestamp:</span>
                        <span>{store.signalTime}</span>
                    </div>
                </div>
            )}
        </div>
      </div>

      {/* Chart Section */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h4 className="text-zinc-100 font-sans font-bold text-xs uppercase tracking-wider">Primary Entry Chart - Futures 3M</h4>
            <div className="h-[400px] bg-zinc-950 border border-zinc-800 rounded-lg flex items-center justify-center">
                 <span className="text-zinc-500 font-mono text-xs uppercase tracking-wider">Interactive Chart (Futures 3M)</span>
            </div>
      </div>

    </div>
  );
};

export default ThreeMinuteGapPanel;
