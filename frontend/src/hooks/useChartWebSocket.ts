import { useState, useEffect, useRef } from 'react';

export default function useChartWebSocket(symbol: string, timeframe: string, historyData: any[]) {
    const [isConnected, setIsConnected] = useState(false);
    const [latestCandle, setLatestCandle] = useState<any>(null);
    const [latestVolume, setLatestVolume] = useState<number>(0);
    const [latestOI, setLatestOI] = useState<number>(0);

    const ws = useRef<WebSocket | null>(null);
    const reconnectTimeout = useRef<any>(null);
    const reconnectAttempts = useRef(0);

    // Parse timeframe to seconds for aggregation
    const tf_map: Record<string, number> = {'1m': 60, '3m': 180, '5m': 300, '15m': 900, '1h': 3600, '1D': 86400};
    const tf_seconds = tf_map[timeframe] || 60;

    const currentCandleRef = useRef<any>(null);

    useEffect(() => {
        if (historyData.length > 0 && !currentCandleRef.current) {
            currentCandleRef.current = { ...historyData[historyData.length - 1] };
        }
    }, [historyData]);

    const heartbeatRef = useRef<number | null>(null);

    const connect = () => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) return;

        ws.current = new WebSocket('ws://localhost:8000/api/v1/chart/stream');

        ws.current.onopen = () => {
            setIsConnected(true);
            reconnectAttempts.current = 0;

            // Start heartbeat ping; store interval id so it can be cleared later
            if (heartbeatRef.current) {
                clearInterval(heartbeatRef.current);
            }
            heartbeatRef.current = window.setInterval(() => {
                if (ws.current?.readyState === WebSocket.OPEN) {
                    try { ws.current.send('ping'); } catch (e) { /* ignore */ }
                }
            }, 5000);
        };

        ws.current.onmessage = (event) => {
            if (!event.data) return;
            if (event.data === 'pong') return;

            try {
                const msg = JSON.parse(event.data);

                // Accept both wrapped messages ({ type, data }) and raw tick objects
                const payload = msg.data ?? msg;

                const instrument = payload.instrument ?? payload.symbol;
                if (instrument && instrument !== symbol) return;

                processTick(payload);
            } catch (err) {
                console.error('Error parsing websocket message', err);
            }
        };

        ws.current.onclose = () => {
            setIsConnected(false);

            // Clear heartbeat
            if (heartbeatRef.current) {
                clearInterval(heartbeatRef.current);
                heartbeatRef.current = null;
            }

            // Exponential backoff
            const timeout = Math.min(10000, 1000 * Math.pow(2, reconnectAttempts.current));
            reconnectAttempts.current += 1;

            reconnectTimeout.current = window.setTimeout(() => {
                connect();
            }, timeout);
        };

        ws.current.onerror = (err) => {
            console.error('WebSocket error:', err);
            try { ws.current?.close(); } catch (e) { /* ignore */ }
        };
    };

    useEffect(() => {
        connect();

        return () => {
            if (ws.current) {
                ws.current.close();
            }
            if (reconnectTimeout.current) {
                clearTimeout(reconnectTimeout.current);
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [symbol, timeframe]);

    const processTick = (tick: any) => {
        // tick expected to contain: instrument/symbol, timestamp, price/ltp, volume, oi
        if (!tick) return;

        const ts = typeof tick.timestamp === 'number' ? tick.timestamp : (new Date(tick.timestamp)).getTime();
        const tickTime = Math.floor(ts / 1000);
        const candleTime = tickTime - (tickTime % tf_seconds);

        let candle = currentCandleRef.current;

        const ltp = tick.price ?? tick.ltp ?? tick.close ?? 0;

        if (!candle || candle.time < candleTime) {
            // New candle
            candle = {
                time: candleTime,
                open: ltp,
                high: ltp,
                low: ltp,
                close: ltp
            };
        } else {
            // Update existing candle
            candle.high = Math.max(candle.high, ltp);
            candle.low = Math.min(candle.low, ltp);
            candle.close = ltp;
        }

        currentCandleRef.current = candle;
        setLatestCandle({ ...candle });
        setLatestVolume(tick.volume ?? 0);
        setLatestOI(tick.oi ?? 0);
    };

    return { isConnected, latestCandle, latestVolume, latestOI };
}
