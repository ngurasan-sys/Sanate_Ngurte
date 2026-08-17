import { useEffect, useRef } from 'react';
import { useAlgoStore } from '../stores/algoStore';
import type { Signal } from '../stores/algoStore';

// This was previously defined but never invoked anywhere in the app, so
// ALGO_DASHBOARD/TRENDING_OI_PA/INTRADAY_TREND_SCALPER's algoStore.signals
// was permanently empty. Now called once, globally, from App.tsx.
//
// Deliberately does NOT touch systemStore's wsStatus/wsLatency —
// useLiveFeedSimulator already owns those for the /ws/levels connection;
// two independent sockets both writing the same global connection-status
// field would flap between CONNECTED/DISCONNECTED as each one's events
// land, unrelated to whether this specific /ws/algo socket is actually up.
export const useAlgoWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const {
    setAlgoEngineStatus,
    addSignal,
    updatePipelineMetrics
  } = useAlgoStore();

  useEffect(() => {
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      ws.current = new WebSocket(`${baseUrl}/ws/algo`);

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
        if (!disposed) setTimeout(connect, 3000);
      };

      ws.current.onerror = () => {
        ws.current?.close();
      };
    };

    connect();

    return () => {
      disposed = true;
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [setAlgoEngineStatus, addSignal, updatePipelineMetrics]);
};
