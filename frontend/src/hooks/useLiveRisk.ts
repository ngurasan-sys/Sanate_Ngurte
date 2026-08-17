import { useEffect } from 'react';
import { useRiskStore } from '../stores/riskStore';

export function useLiveRisk() {
  const setRiskSummary = useRiskStore((s) => s.setRiskSummary);

  useEffect(() => {
    const fetchRisk = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/risk/summary');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.summary) {
          setRiskSummary(data.summary);
        }
      } catch (error) {
        console.warn('Failed to fetch risk summary:', error);
      }
    };

    // Fetch immediately
    fetchRisk();

    // Poll every 5 seconds
    const interval = setInterval(fetchRisk, 5000);
    return () => clearInterval(interval);
  }, [setRiskSummary]);
}
