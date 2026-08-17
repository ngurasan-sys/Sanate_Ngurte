import { useCallback } from 'react';
import { useStrategyStore } from '../stores/strategyStore';
import type { ExecutionMode, TradingMode } from '../stores/strategyStore';

const baseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ReadinessCheck {
  name: string;
  passed: boolean;
  reason: string | null;
}

export interface ReadinessResult {
  strategy_id: string;
  checks: ReadinessCheck[];
  all_passed: boolean;
}

// Thin wrapper over /api/v1/strategy-control/* — every action hits the
// real backend (readiness checks, mutual-exclusivity enforcement) and
// relies on the next useLiveStrategies poll / STRATEGY_CONFIG_CHANGED
// websocket event to reflect the result, rather than optimistically
// mutating local state.
export function useStrategyControl() {
  const refetchStrategies = useCallback(async () => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/strategies`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.strategies && Array.isArray(data.strategies)) {
        useStrategyStore.getState().setStrategies(data.strategies);
      }
    } catch {
      // next poll cycle will pick it up
    }
  }, []);

  const getReadiness = useCallback(async (strategyId: string): Promise<ReadinessResult | null> => {
    try {
      const res = await fetch(`${baseUrl()}/api/v1/strategy-control/${strategyId}/readiness`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }, []);

  const start = useCallback(async (strategyId: string): Promise<{ ok: boolean; detail?: string }> => {
    const res = await fetch(`${baseUrl()}/api/v1/strategy-control/${strategyId}/start`, { method: 'POST' });
    await refetchStrategies();
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, detail: body.detail || `HTTP ${res.status}` };
    }
    return { ok: true };
  }, [refetchStrategies]);

  const stop = useCallback(async (strategyId: string): Promise<{ ok: boolean; detail?: string }> => {
    const res = await fetch(`${baseUrl()}/api/v1/strategy-control/${strategyId}/stop`, { method: 'POST' });
    await refetchStrategies();
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, detail: body.detail || `HTTP ${res.status}` };
    }
    return { ok: true };
  }, [refetchStrategies]);

  const setExecutionMode = useCallback(async (strategyId: string, mode: ExecutionMode) => {
    await fetch(`${baseUrl()}/api/v1/strategy-control/${strategyId}/execution-mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    await refetchStrategies();
  }, [refetchStrategies]);

  const setTradingMode = useCallback(async (strategyId: string, mode: TradingMode) => {
    await fetch(`${baseUrl()}/api/v1/strategy-control/${strategyId}/trading-mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    await refetchStrategies();
  }, [refetchStrategies]);

  const startAll = useCallback(async () => {
    const res = await fetch(`${baseUrl()}/api/v1/strategy-control/start-all`, { method: 'POST' });
    await refetchStrategies();
    return res.ok ? await res.json() : null;
  }, [refetchStrategies]);

  const stopAll = useCallback(async () => {
    const res = await fetch(`${baseUrl()}/api/v1/strategy-control/stop-all`, { method: 'POST' });
    await refetchStrategies();
    return res.ok ? await res.json() : null;
  }, [refetchStrategies]);

  return { start, stop, setExecutionMode, setTradingMode, startAll, stopAll, getReadiness, refetchStrategies };
}
