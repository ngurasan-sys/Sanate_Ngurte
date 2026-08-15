import { useEffect, useRef } from 'react';
import { useOptionAnalyticsStore } from '../stores/optionAnalyticsStore';

export const useOptionAnalyticsWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const { updateState, setConnectionStatus } = useOptionAnalyticsStore();

  useEffect(() => {
    const connect = () => {
      const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      setConnectionStatus('CONNECTING');
      ws.current = new WebSocket(`${baseUrl}/ws/option_analytics`);

      ws.current.onopen = () => {
        setConnectionStatus('CONNECTED');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // The engine publishes a "no token yet" / lookup-failure shape
          // with just {sufficient_data: false, reason: ...} when it can't
          // fetch a chain at all — no timestamp/spot/sub-states in that
          // case. Surface it as a global insufficient-data state rather
          // than crashing on missing nested fields.
          if (data.sufficient_data === false && !data.iv_regime) {
            updateState({
              timestamp: null,
              ivRegime: { sufficientData: false, reason: data.reason, atmIv: null, baselineIv: null, ivChangePct: null, regime: 'UNKNOWN', skew: null, skewBias: 'NEUTRAL', signal: 'NONE', reasoning: null },
              pcrReversal: { sufficientData: false, reason: data.reason, pcr: null, pcrPeak: null, pcrTrough: null, zone: 'NEUTRAL', signal: 'NONE', reasoning: null },
              svi: { sufficientData: false, reason: data.reason, expiry: null, tauYears: null, forward: null, atmIv: null, skew: null, arbitrageFree: null, params: null },
              vrp: { sufficientData: false, reason: data.reason, impliedVol: null, forecastVol: null, vrp: null, zScore: null, classification: 'UNKNOWN', signal: 'NONE' },
            });
            return;
          }

          updateState({
            timestamp: data.timestamp,
            underlyingKey: data.underlying_key,
            spotPrice: data.spot_price,
            atmStrike: data.atm_strike,
            ivRegime: {
              sufficientData: data.iv_regime?.sufficient_data ?? false,
              reason: data.iv_regime?.reason ?? null,
              atmIv: data.iv_regime?.atm_iv ?? null,
              baselineIv: data.iv_regime?.baseline_iv ?? null,
              ivChangePct: data.iv_regime?.iv_change_pct ?? null,
              regime: data.iv_regime?.regime ?? 'UNKNOWN',
              skew: data.iv_regime?.skew ?? null,
              skewBias: data.iv_regime?.skew_bias ?? 'NEUTRAL',
              signal: data.iv_regime?.signal ?? 'NONE',
              reasoning: data.iv_regime?.reasoning ?? null,
            },
            pcrReversal: {
              sufficientData: data.pcr_reversal?.sufficient_data ?? false,
              reason: data.pcr_reversal?.reason ?? null,
              pcr: data.pcr_reversal?.pcr ?? null,
              pcrPeak: data.pcr_reversal?.pcr_peak ?? null,
              pcrTrough: data.pcr_reversal?.pcr_trough ?? null,
              zone: data.pcr_reversal?.zone ?? 'NEUTRAL',
              signal: data.pcr_reversal?.signal ?? 'NONE',
              reasoning: data.pcr_reversal?.reasoning ?? null,
            },
            svi: {
              sufficientData: data.svi?.sufficient_data ?? false,
              reason: data.svi?.reason ?? null,
              expiry: data.svi?.expiry ?? null,
              tauYears: data.svi?.tau_years ?? null,
              forward: data.svi?.forward ?? null,
              atmIv: data.svi?.atm_iv ?? null,
              skew: data.svi?.skew ?? null,
              arbitrageFree: data.svi?.arbitrage_free ?? null,
              params: data.svi?.params ?? null,
            },
            vrp: {
              sufficientData: data.vrp?.sufficient_data ?? false,
              reason: data.vrp?.reason ?? null,
              impliedVol: data.vrp?.implied_vol ?? null,
              forecastVol: data.vrp?.forecast_vol ?? null,
              vrp: data.vrp?.vrp ?? null,
              zScore: data.vrp?.z_score ?? null,
              classification: data.vrp?.classification ?? 'UNKNOWN',
              signal: data.vrp?.signal ?? 'NONE',
            },
          });
        } catch (e) {
          console.error('Error parsing Option Analytics WS message', e);
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
  }, [updateState, setConnectionStatus]);
};
