import { useEffect } from 'react';
import { useTwoCandleStore } from '../stores/twoCandleStore';

// Wires the TWO_CANDLE page to backend/app/strategies/two_candle_engine.py's
// two_candle_state broadcast (ws/two_candle channel). Previously
// setConditions/setSignalData were never called anywhere in production —
// this was the missing live source.
export function useTwoCandleWebSocket(instrument: string = 'NIFTY') {
  const setConditions = useTwoCandleStore((s) => s.setConditions);
  const setSignalData = useTwoCandleStore((s) => s.setSignalData);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      ws = new WebSocket(`${baseUrl}/ws/two_candle`);

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.instrument !== instrument) return;

          if (payload.conditions) setConditions(payload.conditions);
          if (payload.signalData) {
            const sd = payload.signalData;
            setSignalData({
              status: sd.status,
              signal: sd.signal,
              entryTrigger: sd.entry_trigger,
              stopLoss: sd.stop_loss,
              reason: sd.reason,
              currentPrice: payload.currentPrice,
            });
          }
        } catch (e) {
          console.error('Error parsing two_candle WS message', e);
        }
      };

      ws.onclose = () => {
        if (!disposed) setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      disposed = true;
      ws?.close();
    };
  }, [instrument, setConditions, setSignalData]);
}
