import { useEffect, useRef } from 'react';
import { useSystemStore } from '../stores/systemStore';
import { useAlgoStore } from '../stores/algoStore';
import type { Signal } from '../stores/algoStore';

export const useAlgoWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const { setWsStatus, setWsLatency } = useSystemStore();
  const {
    setAlgoEngineStatus,
    addSignal,
    updatePipelineMetrics
  } = useAlgoStore();

  useEffect(() => {
    const connect = () => {
      // Use the existing websocket endpoint that the ConnectionManager listens on.
      // We pass the channel we want, which is 'algo'
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      // Based on main.py the router is mapped, and websockets.py handles /ws/{channel}
      ws.current = new WebSocket(`${baseUrl}/ws/algo`);

      ws.current.onopen = () => {
        setWsStatus('CONNECTED');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.status) {
            setAlgoEngineStatus(data.status);
          } else if (data.type === 'SIGNAL_CREATED') {
            addSignal(data.payload as Signal);
            updatePipelineMetrics({ signalsGenerated: 1 }); // increment
          } else if (data.type === 'EXECUTION_UPDATE') {
             // Handle execution update
          }
          // Note: In a full app you'd map all events specifically.
        } catch (e) {
          console.error('Error parsing algo WS message', e);
        }
      };

      ws.current.onclose = () => {
        setWsStatus('DISCONNECTED');
        setTimeout(connect, 3000);
      };

      ws.current.onerror = () => {
        setWsStatus('DISCONNECTED');
      };
    };

    connect();

    // Ping mechanism
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        const start = performance.now();
        ws.current.send('ping');
        setWsLatency(Math.round(performance.now() - start));
      }
    }, 5000);

    return () => {
      clearInterval(pingInterval);
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [setWsStatus, setWsLatency, setAlgoEngineStatus, addSignal, updatePipelineMetrics]);
};
