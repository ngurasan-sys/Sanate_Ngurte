import { useEffect } from 'react';
import { useMarketStore } from '../stores/marketStore';

export function useLiveMarketIndices() {
  const setIndices = useMarketStore((s) => s.setIndices);

  useEffect(() => {
    const fetchMarketIndices = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/market/indices');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.indices && Object.keys(data.indices).length > 0) {
          const formatted = Object.fromEntries(
            Object.entries(data.indices).map(([key, value]: [string, any]) => [
              key,
              {
                spot: value.spot,
                change: value.change,
                changePercent: value.changePercent,
                dayHigh: value.dayHigh,
                dayLow: value.dayLow,
                vwap: value.vwap,
                support: value.support,
                resistance: value.resistance,
                iv: value.iv,
                expectedMove: value.expectedMove,
                oiRegime: value.oiRegime,
                diffOiPct: value.diffOiPct,
              }
            ])
          );
          setIndices(formatted as Record<'NIFTY' | 'SENSEX', any>);
        }
      } catch (error) {
        console.warn('Failed to fetch market indices:', error);
      }
    };

    // Fetch immediately
    fetchMarketIndices();

    // Poll every 5 seconds
    const interval = setInterval(fetchMarketIndices, 5000);
    return () => clearInterval(interval);
  }, [setIndices]);
}
