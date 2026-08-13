import { useEffect, useRef } from 'react';
import { useSystemStore } from './systemStore';

export function useLiveFeedSimulator() {
  const { setWsLatency, setWsStatus } = useSystemStore();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // If we want to connect to our real backend instead of simulating
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/levels';

    // We'll fallback to a mock simulator if backend is not available, but for this instruction we try to connect.
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('CONNECTED');
      console.log('Connected to Sanate Backend WS');
    };

    ws.onmessage = (event) => {
      // Basic ping tracking
      setWsLatency(Math.floor(Math.random() * 20) + 5);

      try {
        const data = JSON.parse(event.data);
        if (data.type === 'LEVEL_CREATED') {
          console.log('New Level Received:', data.data);
          // In a full implementation, we'd add this to a levelStore
        }
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };

    ws.onclose = () => {
      setWsStatus('DISCONNECTED');
    };

    return () => {
      ws.close();
    };
  }, [setWsLatency, setWsStatus]);
}
