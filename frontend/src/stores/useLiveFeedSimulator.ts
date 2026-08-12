import { useEffect } from 'react';
import { useMarketStore } from './marketStore';
import { useOptionStore } from './optionStore';
import { usePortfolioStore } from './portfolioStore';
import { useSystemStore } from './systemStore';

function getSecureRandom(): number {
  const array = new Uint32Array(1);
  window.crypto.getRandomValues(array);
  return array[0] / (0xffffffff + 1);
}

// Hook to simulate a live Websocket data stream.
// This executes updates periodically in a stable, incremental fashion.
export function useLiveFeedSimulator() {
  const { indices, updateIndexPrice } = useMarketStore();
  const { updateLtp } = useOptionStore();
  const { positions, updatePositionPrice } = usePortfolioStore();
  const { brokerageStatus, setWsLatency } = useSystemStore();

  useEffect(() => {
    if (brokerageStatus.wsStatus !== 'CONNECTED') return;

    const interval = setInterval(() => {
      // 1. Randomize WebSocket latency slightly
      const newLatency = Math.max(4, Math.min(45, brokerageStatus.wsLatency + (getSecureRandom() > 0.5 ? 1 : -1) * Math.floor(getSecureRandom() * 3)));
      setWsLatency(newLatency);

      // 2. Incremental updates for NIFTY & SENSEX spot prices
      const nifty = indices.NIFTY;
      const niftyChange = (getSecureRandom() - 0.48) * 1.5; // slight bullish bias
      const newNiftySpot = parseFloat((nifty.spot + niftyChange).toFixed(2));
      const newNiftyDiff = parseFloat((nifty.change + niftyChange).toFixed(2));
      const newNiftyPct = parseFloat(((newNiftyDiff / (24500 - nifty.change)) * 100).toFixed(2));
      updateIndexPrice('NIFTY', newNiftySpot, newNiftyDiff, newNiftyPct);

      const sensex = indices.SENSEX;
      const sensexChange = (getSecureRandom() - 0.52) * 4.0; // slight bearish bias
      const newSensexSpot = parseFloat((sensex.spot + sensexChange).toFixed(2));
      const newSensexDiff = parseFloat((sensex.change + sensexChange).toFixed(2));
      const newSensexPct = parseFloat(((newSensexDiff / (80240 - sensex.change)) * 100).toFixed(2));
      updateIndexPrice('SENSEX', newSensexSpot, newSensexDiff, newSensexPct);

      // 3. Option chain live update for NIFTY ATM (24500 CE/PE)
      const cePriceDelta = (getSecureRandom() - 0.45) * 0.40;
      updateLtp('NIFTY', 24500, 'ce', parseFloat(Math.max(10, 112.50 + cePriceDelta).toFixed(2)));

      const pePriceDelta = (getSecureRandom() - 0.55) * 0.40;
      updateLtp('NIFTY', 24500, 'pe', parseFloat(Math.max(10, 108.20 + pePriceDelta).toFixed(2)));

      // 4. Update Position P&L and LTP based on changes
      positions.forEach((pos) => {
        if (pos.status === 'ACTIVE') {
          const ltpChange = (getSecureRandom() - 0.47) * 0.25;
          const updatedLtp = parseFloat(Math.max(5, pos.ltp + ltpChange).toFixed(2));
          updatePositionPrice(pos.id, updatedLtp);
        }
      });
    }, 1500); // stable interval to avoid rendering overwhelm

    return () => clearInterval(interval);
  }, [brokerageStatus.wsStatus, indices, positions, updateIndexPrice, updateLtp, updatePositionPrice, setWsLatency, brokerageStatus.wsLatency]);
}
export default useLiveFeedSimulator;
