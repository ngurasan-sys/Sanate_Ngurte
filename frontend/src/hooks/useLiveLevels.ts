import { useCallback, useEffect, useState } from 'react';
import type { LiveLevel } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawLevel {
  level_id: string; price: number; level_type: 'Support' | 'Resistance';
  timeframe: string; strength: number; touch_count: number;
}

export function useLiveLevels(instrument: string) {
  const [levels, setLevels] = useState<LiveLevel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/levels/${encodeURIComponent(instrument)}`);
      if (!res.ok) throw new Error(`levels fetch failed (${res.status})`);
      const raw: RawLevel[] = await res.json();
      setLevels(raw.map((r) => ({
        levelId: r.level_id,
        price: r.price,
        levelType: r.level_type,
        timeframe: r.timeframe,
        strength: r.strength,
        touchCount: r.touch_count,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load levels');
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { levels, loading, error, refetch };
}
