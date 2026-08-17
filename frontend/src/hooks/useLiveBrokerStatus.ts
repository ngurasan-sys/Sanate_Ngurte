import { useEffect } from 'react';
import { useSystemStore } from '../stores/systemStore';

// BrokeragePanel used to track connected/disconnected purely in local
// zustand state — its "DISCONNECT" button made zero backend calls, so an
// operator could believe a broker was disconnected while it was still
// live server-side. This hook polls the real backend truth
// (GET /api/v1/brokers/{id}/status, backed by active_broker) and reflects
// it into systemStore, so the panel can never drift from what's actually
// connected.
export function useLiveBrokerStatus(brokerId: string = 'upstox') {
  const setBrokerageStatus = useSystemStore((s) => s.setBrokerageStatus);
  const brokerageStatus = useSystemStore((s) => s.brokerageStatus);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const response = await fetch(`${baseUrl}/api/v1/brokers/${brokerId}/status`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        setBrokerageStatus({
          ...brokerageStatus,
          isConnected: !!data.connected,
          account: {
            ...brokerageStatus.account,
            authStatus: data.connected ? 'AUTHENTICATED' : 'AUTHENTICATION REQUIRED',
          },
        });
      } catch (error) {
        console.warn('Failed to fetch broker status:', error);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brokerId, setBrokerageStatus]);
}
