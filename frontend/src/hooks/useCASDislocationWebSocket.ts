import { useEffect, useRef } from 'react';
import { useCASDislocationStore } from '../stores/casDislocationStore';

export const useCASDislocationWebSocket = () => {
  const readingWs = useRef<WebSocket | null>(null);
  const positionsWs = useRef<WebSocket | null>(null);
  const { setReading, setPositions, setConnectionStatus } = useCASDislocationStore();

  useEffect(() => {
    const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
    let readingConnected = false;
    let positionsConnected = false;
    const updateStatus = () => {
      setConnectionStatus(readingConnected && positionsConnected ? 'CONNECTED' : 'CONNECTING');
    };

    const connectReading = () => {
      setConnectionStatus('CONNECTING');
      readingWs.current = new WebSocket(`${baseUrl}/ws/cas_dislocation`);

      readingWs.current.onopen = () => { readingConnected = true; updateStatus(); };
      readingWs.current.onmessage = (event) => {
        try {
          setReading(JSON.parse(event.data));
        } catch (e) {
          console.error('Error parsing CAS Dislocation WS message', e);
        }
      };
      readingWs.current.onclose = () => { readingConnected = false; updateStatus(); setTimeout(connectReading, 3000); };
      readingWs.current.onerror = () => { readingConnected = false; updateStatus(); };
    };

    const connectPositions = () => {
      positionsWs.current = new WebSocket(`${baseUrl}/ws/cas_dislocation_positions`);

      positionsWs.current.onopen = () => { positionsConnected = true; updateStatus(); };
      positionsWs.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (Array.isArray(data.positions)) setPositions(data.positions);
        } catch (e) {
          console.error('Error parsing CAS Dislocation positions WS message', e);
        }
      };
      positionsWs.current.onclose = () => { positionsConnected = false; updateStatus(); setTimeout(connectPositions, 3000); };
      positionsWs.current.onerror = () => { positionsConnected = false; updateStatus(); };
    };

    connectReading();
    connectPositions();

    const pingInterval = setInterval(() => {
      if (readingWs.current?.readyState === WebSocket.OPEN) readingWs.current.send('ping');
      if (positionsWs.current?.readyState === WebSocket.OPEN) positionsWs.current.send('ping');
    }, 5000);

    return () => {
      clearInterval(pingInterval);
      readingWs.current?.close();
      positionsWs.current?.close();
    };
  }, [setReading, setPositions, setConnectionStatus]);
};
