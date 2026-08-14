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

    const connect = () => {
        if (ws.current?.readyState === WebSocket.OPEN) return;

        ws.current = new WebSocket('ws://localhost:8000/api/v1/chart/stream');

        ws.current.onopen = () => {
            setIsConnected(true);
            reconnectAttempts.current = 0;

            // Start heartbeat ping
            setInterval(() => {
                if (ws.current?.readyState === WebSocket.OPEN) {
                    ws.current.send('ping');
                }
            }, 5000);
        };

        ws.current.onmessage = (event) => {
            if (event.data === 'pong') return;

            try {
                const tick = JSON.parse(event.data);
                if (tick.type === 'tick' && tick.symbol === symbol) {
                    processTick(tick);
                }
            } catch (err) {
                console.error("Error parsing websocket message", err);
            }
        };

        ws.current.onclose = () => {
            setIsConnected(false);

            // Exponential backoff
            const timeout = Math.min(10000, 1000 * Math.pow(2, reconnectAttempts.current));
            reconnectAttempts.current += 1;

            reconnectTimeout.current = setTimeout(() => {
                connect();
            }, timeout);
        };

        ws.current.onerror = (err) => {
            console.error("WebSocket error:", err);
            ws.current?.close();
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
        if (ws.current?.readyState === WebSocket.OPEN) return;

        ws.current = new WebSocket('ws://localhost:8000/api/v1/chart/stream');

        ws.current.onopen = () => {
            setIsConnected(true);
            reconnectAttempts.current = 0;

            // Start heartbeat ping
            setInterval(() => {
                if (ws.current?.readyState === WebSocket.OPEN) {
                    ws.current.send('ping');
                }
            }, 5000);
        };

        ws.current.onmessage = (event) => {
            if (event.data === 'pong') return;

            try {
                const tick = JSON.parse(event.data);
                if (tick.type === 'tick' && tick.symbol === symbol) {
                    processTick(tick);
                }
            } catch (err) {
                console.error("Error parsing websocket message", err);
            }
        };

        ws.current.onclose = () => {
            setIsConnected(false);

            // Exponential backoff
            const timeout = Math.min(10000, 1000 * Math.pow(2, reconnectAttempts.current));
            reconnectAttempts.current += 1;

            reconnectTimeout.current = setTimeout(() => {
                connect();
            }, timeout);
        };

        const tickTime = Math.floor(tick.timestamp / 1000);
        const candleTime = tickTime - (tickTime % tf_seconds);

        let candle = currentCandleRef.current;

        if (!candle || candle.time < candleTime) {
            // New candle
            candle = {
                time: candleTime,
                open: tick.ltp,
                high: tick.ltp,
                low: tick.ltp,
                close: tick.ltp
            };
        } else {
            // Update existing candle
            candle.high = Math.max(candle.high, tick.ltp);
            candle.low = Math.min(candle.low, tick.ltp);
            candle.close = tick.ltp;
        }

        currentCandleRef.current = candle;
        setLatestCandle({ ...candle });
        setLatestVolume(tick.volume);
        setLatestOI(tick.oi);
    };

    return { isConnected, latestCandle, latestVolume, latestOI };
}
