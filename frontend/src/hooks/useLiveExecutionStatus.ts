import { useEffect } from 'react';
import { useAlgoStore } from '../stores/algoStore';
import type { ExecutionMode } from '../stores/algoStore';

const RESOLVED_MODE_TO_UI: Record<string, ExecutionMode> = {
  DRY_RUN: 'DATA_ONLY',
  SANDBOX: 'PAPER',
  LIVE: 'LIVE',
};

// Polls the REAL execution-mode source of truth (order_gateway.resolve_mode()
// via execution_control.py) and reflects it into algoStore, so the Algo
// Dashboard's execution-mode badge can never drift from what the backend
// will actually do with an order. This is a read of existing backend state,
// not a second execution-mode system — arming/disarming still goes through
// /api/v1/execution/arm and /disarm (see handleModeChange in AlgoDashboardView).
export function useLiveExecutionStatus() {
  const setExecutionMode = useAlgoStore((s) => s.setExecutionMode);
  const setArmed = useAlgoStore((s) => s.setArmed);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const response = await fetch(`${baseUrl}/api/v1/execution/status`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        const resolvedMode = data.resolved_mode as string | undefined;
        if (resolvedMode && RESOLVED_MODE_TO_UI[resolvedMode]) {
          setExecutionMode(RESOLVED_MODE_TO_UI[resolvedMode]);
        }
        if (typeof data.armed === 'boolean') {
          setArmed(data.armed);
        }
      } catch (error) {
        console.warn('Failed to fetch execution status:', error);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [setExecutionMode, setArmed]);
}
