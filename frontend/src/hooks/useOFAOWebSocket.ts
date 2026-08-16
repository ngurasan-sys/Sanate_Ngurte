import { useEffect, useRef } from 'react';
import { useOFAOStore } from '../stores/useOFAOStore';

export const useOFAOWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const { applySnapshot, setConnectionStatus } = useOFAOStore();

  useEffect(() => {
    const connect = () => {
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      setConnectionStatus('CONNECTING');
      ws.current = new WebSocket(`${baseUrl}/ws/ofao`);

      ws.current.onopen = () => {
        setConnectionStatus('CONNECTED');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!data.instrument_key) return;
          applySnapshot(data);
        } catch (e) {
          console.error('Error parsing OFAO WS message', e);
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
  }, [applySnapshot, setConnectionStatus]);
};
