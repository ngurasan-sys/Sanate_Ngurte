import { useCallback, useEffect, useState } from 'react';
import type { LivePosition } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawManualPosition {
  position_id: string; underlying: string; option_type: 'CE' | 'PE'; strike: number;
  quantity: number; entry_price: number; status: 'PENDING' | 'OPEN' | 'CLOSED';
  created_at: string; closed_at: string | null; exit_reason: string | null;
}

interface RawCASPosition extends RawManualPosition {}

function toLivePosition(raw: RawManualPosition, source: 'MANUAL' | 'CAS'): LivePosition {
  return {
    id: `${source}_${raw.position_id}`,
    source,
    instrument: `${raw.underlying} ${raw.strike} ${raw.option_type}`,
    strike: raw.strike,
    optionType: raw.option_type,
    quantity: raw.quantity,
    entryPrice: raw.entry_price,
    status: raw.status,
    createdAt: raw.created_at,
    closedAt: raw.closed_at,
    exitReason: raw.exit_reason,
  };
}

export function useLivePositions() {
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [manualRes, casRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/manual-trading/positions`),
        fetch(`${API_BASE}/api/v1/cas-dislocation/positions`),
      ]);
      if (!manualRes.ok) throw new Error(`manual-trading/positions failed (${manualRes.status})`);
      if (!casRes.ok) throw new Error(`cas-dislocation/positions failed (${casRes.status})`);
      const manual: RawManualPosition[] = await manualRes.json();
      const cas: RawCASPosition[] = await casRes.json();
      setPositions([
        ...manual.map((p) => toLivePosition(p, 'MANUAL')),
        ...cas.map((p) => toLivePosition(p, 'CAS')),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { positions, loading, error, refetch };
}
