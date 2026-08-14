import { useEffect, useRef } from 'react';
import { useSystemStore } from './systemStore';

/**
 * Cryptographically secure random number in [0, 1).
 *
 * Used only for frontend simulation of WebSocket latency.
 * Market data must come from the backend WebSocket.
 */
function getSecureRandom(): number {
  const array = new Uint32Array(1);
  window.crypto.getRandomValues(array);
  return array[0] / 0x100000000;
}

/**
 * Live Sanate backend WebSocket feed.
 *
 * Backend is the source of truth for market/level data.
 * This hook only manages the WebSocket connection and
 * updates system connection state.
 */
export function useLiveFeedSimulator() {
  const { setWsLatency, setWsStatus } = useSystemStore();

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl =
      import.meta.env.VITE_WS_URL ||
      'ws://localhost:8000/ws/levels';

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) {
        return;
      }

      try {
        console.log(`[Sanate] Connecting to WebSocket: ${wsUrl}`);

        setWsStatus('RECONNECTING');

        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (disposed) {
            return;
          }

          console.log('[Sanate] Backend WebSocket connected');

          setWsStatus('CONNECTED');

          // Reset the displayed latency when the connection opens.
          setWsLatency(5);
        };

        ws.onmessage = (event: MessageEvent<string>) => {
          if (disposed) {
            return;
          }

          /*
           * The backend is the source of truth.
           *
           * We do NOT generate NIFTY, SENSEX, option prices,
           * positions, OI, levels, etc. here.
           */

          // Estimate/display WebSocket latency.
          // This randomness is UI-only and is not market data.
          const latency = Math.floor(getSecureRandom() * 20) + 5;

          setWsLatency(latency);

          try {
            const data = JSON.parse(event.data);

            console.debug('[Sanate] WebSocket event:', data);

            /*
             * Level events are currently logged here.
             *
             * A dedicated levelStore can consume these events
             * when the frontend level-state integration is enabled.
             */
            if (data?.type === 'LEVEL_CREATED') {
              console.log(
                '[Sanate] New level received:',
                data.data
              );
            }

            if (data?.type === 'LEVEL_UPDATED') {
              console.log(
                '[Sanate] Level updated:',
                data.data
              );
            }

            if (data?.type === 'LEVEL_REMOVED') {
              console.log(
                '[Sanate] Level removed:',
                data.data
              );
            }

            /*
             * Generic backend events.
             *
             * Keeping this generic allows future Sanate engines
             * to publish events without requiring this hook to
             * understand every event type.
             */
            if (data?.type) {
              console.debug(
                `[Sanate] Event type: ${data.type}`
              );
            }
          } catch (error) {
            console.error(
              '[Sanate] WebSocket JSON parse error:',
              error
            );
          }
        };

        ws.onerror = (error) => {
          if (disposed) {
            return;
          }

          console.error(
            '[Sanate] WebSocket error:',
            error
          );

          setWsStatus('DISCONNECTED');
        };

        ws.onclose = (event) => {
          if (disposed) {
            return;
          }

          console.warn(
            `[Sanate] WebSocket disconnected. Code=${event.code}`
          );

          setWsStatus('DISCONNECTED');

          wsRef.current = null;

          /*
           * Reconnect automatically.
           *
           * 2-second delay prevents a tight reconnect loop
           * when the backend is unavailable.
           */
          reconnectTimer = setTimeout(() => {
            if (!disposed) {
              connect();
            }
          }, 2000);
        };
      } catch (error) {
        console.error(
          '[Sanate] Failed to create WebSocket:',
          error
        );

        setWsStatus('DISCONNECTED');

        reconnectTimer = setTimeout(() => {
          if (!disposed) {
            connect();
          }
        }, 2000);
      }
    };

    connect();

    return () => {
      disposed = true;

      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }

      if (ws) {
        /*
         * Remove handlers before closing so the intentional
         * component cleanup does not trigger a reconnect.
         */
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;

        if (
          ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING
        ) {
          ws.close();
        }
      }

      wsRef.current = null;
    };
  }, [setWsLatency, setWsStatus]);
}