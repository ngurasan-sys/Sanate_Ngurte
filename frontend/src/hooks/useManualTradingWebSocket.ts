import { useEffect, useRef } from 'react';
import { useManualTradingStore } from '../stores/manualTradingStore';

export const useManualTradingWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const { setPositions, setConnectionStatus } = useManualTradingStore();

  useEffect(() => {
    const connect = () => {
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      setConnectionStatus('CONNECTING');
      ws.current = new WebSocket(`${baseUrl}/ws/manual_trading`);

      ws.current.onopen = () => {
        setConnectionStatus('CONNECTED');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (Array.isArray(data.positions)) {
            setPositions(data.positions);
          }
        } catch (e) {
          console.error('Error parsing Manual Trading WS message', e);
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
  }, [setPositions, setConnectionStatus]);
};
