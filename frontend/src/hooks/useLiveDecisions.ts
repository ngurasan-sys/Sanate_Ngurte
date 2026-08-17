import { useEffect } from 'react';
import { useDecisionStore } from '../stores/decisionStore';

export function useLiveDecisions() {
  const setDecisions = useDecisionStore((s) => s.setDecisions);

  useEffect(() => {
    const fetchDecisions = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/decisions');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.decisions && Array.isArray(data.decisions)) {
          setDecisions(data.decisions);
        }
      } catch (error) {
        console.warn('Failed to fetch decisions:', error);
      }
    };

    // Fetch immediately
    fetchDecisions();

    // Poll every 5 seconds
    const interval = setInterval(fetchDecisions, 5000);
    return () => clearInterval(interval);
  }, [setDecisions]);
}
