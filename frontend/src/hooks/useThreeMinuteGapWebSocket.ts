import { useEffect } from 'react';
import { useThreeMinuteGapStore } from '../stores/threeMinuteGapStore';

// Wires the THREE_MINUTE_GAP page to
// backend/app/strategies/three_minute_gap/engine.py's three_minute_gap_state
// broadcast (ws/three_minute_gap channel). Previously this page had no
// backend engine at all and no live wiring whatsoever.
export function useThreeMinuteGapWebSocket(instrument: string = 'NIFTY') {
  const setConnected = useThreeMinuteGapStore((s) => s.setConnected);
  const updateState = useThreeMinuteGapStore((s) => s.updateState);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      ws = new WebSocket(`${baseUrl}/ws/three_minute_gap`);

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!disposed) setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();

      ws.onmessage = (event) => {
        try {
          const p = JSON.parse(event.data);
          if (p.instrument !== instrument) return;

          updateState({
            isConnected: p.isConnected,
            strategyStatus: p.strategyStatus,
            underlying: p.underlying,
            executionMode: p.executionMode,
            futuresPrice: p.futuresPrice,
            threeMinTrend: p.threeMinTrend,
            superTrend: p.superTrend,
            vwap: p.vwap,
            dayHigh: p.dayHigh,
            dayLow: p.dayLow,
            gapType: p.gapType,
            gapBase: p.gapBase,
            gapTop: p.gapTop,
            gapStatus: p.gapStatus,
            diffOi: p.diffOi,
            diffOiPercent: p.diffOiPercent,
            strengthDots: p.strengthDots,
            sentiment: p.sentiment,
            pullbackStatus: p.pullbackStatus,
            superTrendInteraction: p.superTrendInteraction,
            fvgInteraction: p.fvgInteraction,
            entryStatus: p.entryStatus,
            signalAction: p.signalAction,
            signalReason: p.signalReason,
            signalTime: p.signalTime,
          });
        } catch (e) {
          console.error('Error parsing three_minute_gap WS message', e);
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      ws?.close();
    };
  }, [instrument, setConnected, updateState]);
}
