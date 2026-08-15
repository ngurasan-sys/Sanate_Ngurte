import React, { useEffect, useState } from 'react';
import { Layers, TrendingUp, X } from 'lucide-react';
import { useManualTradingStore } from '../stores/manualTradingStore';
import { useManualTradingWebSocket } from '../hooks/useManualTradingWebSocket';
import StatusBadge from './StatusBadge';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Underlying = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

export const ManualTradingPanel: React.FC = () => {
  useManualTradingWebSocket();
  const { lotSizes, positions, setLotSizes, connectionStatus } = useManualTradingStore();

  const [underlying, setUnderlying] = useState<Underlying>('NIFTY');
  const [optionType, setOptionType] = useState<'CE' | 'PE'>('CE');
  const [strike, setStrike] = useState('');
  const [lots, setLots] = useState('1');
  const [stopLoss, setStopLoss] = useState('');
  const [target, setTarget] = useState('');
  const [pyramidLotSize, setPyramidLotSize] = useState('0');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${baseUrl()}/api/v1/manual-trading/lot-sizes`)
      .then((r) => r.json())
      .then(setLotSizes)
      .catch((e) => console.error('Failed to fetch lot sizes', e));
  }, [setLotSizes]);

  const lotSize = lotSizes[underlying] || 0;
  const lotsNum = parseInt(lots, 10) || 0;
  const quantity = lotsNum * lotSize;

  const handlePlaceOrder = async () => {
    setError(null);
    const stopLossNum = parseFloat(stopLoss);
    const targetNum = parseFloat(target);

    if (lotsNum <= 0) return setError('Lots must be a positive number.');
    if (isNaN(stopLossNum) || isNaN(targetNum)) return setError('Stop loss and target are required.');
    if (stopLossNum >= targetNum) return setError('Stop loss must be less than target.');

    setSubmitting(true);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/manual-trading/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying,
          option_type: optionType,
          strike: strike ? parseFloat(strike) : null,
          lots: lotsNum,
          stop_loss: stopLossNum,
          target: targetNum,
          pyramid_lot_size: parseInt(pyramidLotSize, 10) || 0,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.detail || 'Order rejected.');
      }
    } catch {
      setError('Failed to reach the backend — is it running?');
    } finally {
      setSubmitting(false);
    }
  };

  const handlePyramid = async (positionId: string) => {
    setActionError(null);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/manual-trading/pyramid/${positionId}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) setActionError(body.detail || 'Pyramid add rejected.');
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  const handleClose = async (positionId: string) => {
    setActionError(null);
    try {
      const response = await fetch(`${baseUrl()}/api/v1/manual-trading/close/${positionId}`, { method: 'POST' });
      const body = await response.json();
      if (!response.ok) setActionError(body.detail || 'Close rejected.');
    } catch {
      setActionError('Failed to reach the backend.');
    }
  };

  // PENDING (submitted, awaiting risk/execution confirmation) shows in the
  // same table as OPEN — it's still an active position from the trader's
  // point of view, just not confirmed yet. A dedicated Status column makes
  // the distinction visible rather than hiding it.
  const activePositions = positions.filter((p) => p.status === 'OPEN' || p.status === 'PENDING');
  const closedPositions = positions.filter((p) => p.status === 'CLOSED');

  return (
    <div className="space-y-6 select-none">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-emerald-400" />
            <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Place Manual Order</h3>
          </div>
          <StatusBadge status={connectionStatus} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Underlying</label>
            <select
              value={underlying}
              onChange={(e) => setUnderlying(e.target.value as Underlying)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            >
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
              <option value="SENSEX">SENSEX</option>
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Option Type</label>
            <div className="flex gap-1">
              <button
                onClick={() => setOptionType('CE')}
                className={`flex-1 rounded px-2 py-1.5 font-bold ${optionType === 'CE' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-950 border border-zinc-800 text-zinc-400'}`}
              >
                CE
              </button>
              <button
                onClick={() => setOptionType('PE')}
                className={`flex-1 rounded px-2 py-1.5 font-bold ${optionType === 'PE' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-zinc-950 border border-zinc-800 text-zinc-400'}`}
              >
                PE
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Strike (blank = ATM)</label>
            <input
              type="number"
              value={strike}
              onChange={(e) => setStrike(e.target.value)}
              placeholder="ATM"
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Lots</label>
            <input
              type="number"
              min={1}
              value={lots}
              onChange={(e) => setLots(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Stop Loss (premium ₹)</label>
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Target (premium ₹)</label>
            <input
              type="number"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Pyramid Lot Size</label>
            <input
              type="number"
              min={0}
              value={pyramidLotSize}
              onChange={(e) => setPyramidLotSize(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-200 font-mono rounded px-2 py-1.5 outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-zinc-500 uppercase tracking-wider">Quantity (auto)</label>
            <div className="bg-zinc-950 border border-zinc-850 text-zinc-300 font-mono rounded px-2 py-1.5">
              {lotsNum} x {lotSize || '--'} = <span className="text-zinc-100 font-bold">{quantity}</span>
            </div>
          </div>
        </div>

        {error && (
          <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">
            {error}
          </div>
        )}

        <button
          onClick={handlePlaceOrder}
          disabled={submitting || lotSize === 0}
          className="w-full py-2.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs font-bold tracking-wider uppercase"
        >
          {submitting ? 'Placing Order…' : `Buy ${underlying} ${optionType}`}
        </button>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <Layers size={18} className="text-sky-400" />
          <h3 className="text-zinc-100 font-sans font-bold text-sm tracking-wider uppercase">Manual Positions</h3>
        </div>

        {actionError && (
          <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2 mb-3">
            {actionError}
          </div>
        )}

        {activePositions.length === 0 ? (
          <div className="text-center py-6 text-zinc-500 font-mono text-xs uppercase tracking-wider border border-dashed border-zinc-800 rounded">
            NO OPEN MANUAL POSITIONS
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left whitespace-nowrap">
              <thead className="text-zinc-500 border-b border-zinc-800">
                <tr>
                  <th className="pb-2 font-normal uppercase">Instrument</th>
                  <th className="pb-2 font-normal uppercase">Status</th>
                  <th className="pb-2 font-normal uppercase text-right">Qty</th>
                  <th className="pb-2 font-normal uppercase text-right">Entry</th>
                  <th className="pb-2 font-normal uppercase text-right">LTP</th>
                  <th className="pb-2 font-normal uppercase text-right">SL</th>
                  <th className="pb-2 font-normal uppercase text-right">Target</th>
                  <th className="pb-2 font-normal uppercase text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-850 text-zinc-300">
                {activePositions.map((p) => {
                  const pnl = p.last_ltp !== null ? (p.last_ltp - p.entry_price) * p.quantity : null;
                  const isOpen = p.status === 'OPEN';
                  return (
                    <tr key={p.position_id} className="hover:bg-zinc-800/30">
                      <td className="py-2">
                        <span className={p.option_type === 'CE' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                          {p.underlying} {p.strike} {p.option_type}
                        </span>
                        <span className="text-zinc-500 ml-2">({p.lots} lots)</span>
                      </td>
                      <td className="py-2"><StatusBadge status={p.status} /></td>
                      <td className="py-2 text-right">{p.quantity}</td>
                      <td className="py-2 text-right">₹{p.entry_price.toFixed(2)}</td>
                      <td className="py-2 text-right">
                        {p.last_ltp !== null ? (
                          <span className={pnl !== null && pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                            ₹{p.last_ltp.toFixed(2)}
                          </span>
                        ) : '--'}
                      </td>
                      <td className="py-2 text-right text-rose-400">₹{p.stop_loss.toFixed(2)}</td>
                      <td className="py-2 text-right text-emerald-400">₹{p.target.toFixed(2)}</td>
                      <td className="py-2 text-right">
                        {isOpen ? (
                          <div className="flex gap-1 justify-end">
                            {p.pyramid_lot_size > 0 && (
                              <button
                                onClick={() => handlePyramid(p.position_id)}
                                className="px-2 py-1 bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded hover:bg-sky-500/20 text-[10px] font-bold uppercase"
                              >
                                +{p.pyramid_lot_size} Lot
                              </button>
                            )}
                            <button
                              onClick={() => handleClose(p.position_id)}
                              className="px-2 py-1 bg-zinc-800 text-zinc-300 border border-zinc-700 rounded hover:bg-rose-500/20 hover:text-rose-400 hover:border-rose-500/20 text-[10px] font-bold uppercase flex items-center gap-1"
                            >
                              <X size={10} /> Close
                            </button>
                          </div>
                        ) : (
                          <span className="text-zinc-600 text-[10px] uppercase">Awaiting confirmation…</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {closedPositions.length > 0 && (
          <div className="mt-4 pt-4 border-t border-zinc-850">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-2">Recently Closed</p>
            <div className="space-y-1">
              {closedPositions.slice(0, 5).map((p) => (
                <div key={p.position_id} className="flex justify-between text-xs font-mono text-zinc-500">
                  <span>{p.underlying} {p.strike} {p.option_type} ({p.lots} lots)</span>
                  <StatusBadge status={p.exit_reason || 'CLOSED'} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ManualTradingPanel;
