// frontend/src/hooks/useLiveOrders.ts
import { useCallback, useEffect, useState } from 'react';
import type { LiveOrder } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawExecution {
  timestamp: string; instrument: string; action: string; status: string;
}

export function useLiveOrders() {
  const [orders, setOrders] = useState<LiveOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/executions`);
      if (!res.ok) throw new Error(`executions fetch failed (${res.status})`);
      const raw: RawExecution[] = await res.json();
      setOrders(raw.map((r, i) => ({
        id: `${r.timestamp}_${i}`,
        timestamp: r.timestamp,
        instrument: r.instrument,
        action: r.action,
        status: r.status,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load executions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { orders, loading, error, refetch };
}
