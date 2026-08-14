import { useEffect, useRef } from 'react';
import { useChopFilterStore } from '../stores/useChopFilterStore';

export const useChopFilterWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const { updateState, setConnectionStatus } = useChopFilterStore();

  useEffect(() => {
    const connect = () => {
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      setConnectionStatus('CONNECTING');
      ws.current = new WebSocket(`${baseUrl}/ws/pullback_chop`);

      ws.current.onopen = () => {
        setConnectionStatus('CONNECTED');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          updateState({
            timestamp: data.timestamp,
            symbol: data.symbol,
            priceData: {
                ltp: data.price_data?.ltp || 0.0,
                vwap: data.price_data?.vwap || 0.0,
                supertrend: data.price_data?.supertrend || 0.0,
                upperBand: data.price_data?.upper_band || 0.0,
                lowerBand: data.price_data?.lower_band || 0.0,
            },
            oiData: {
                diffPct: data.oi_data?.diff_pct || 0.0
            },
            marketState: data.market_state,
            internalState: data.internal_state,
            activeSignal: data.active_signal
          });
        } catch (e) {
          console.error('Error parsing Pullback Chop Filter WS message', e);
        }
      };

      ws.current.onclose = () => {
        setConnectionStatus('DISCONNECTED');
        setTimeout(connect, 3000);
      };

      ws.current.onerror = () => {
        setConnectionStatus('DISCONNECTED');
      };
    };

    connect();

    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send('ping');
      }
    }, 5000);

    return () => {
      clearInterval(pingInterval);
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [updateState, setConnectionStatus]);
};
