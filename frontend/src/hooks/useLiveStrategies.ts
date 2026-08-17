import { useEffect } from 'react';
import { useStrategyStore } from '../stores/strategyStore';

export function useLiveStrategies() {
  const setStrategies = useStrategyStore((s) => s.setStrategies);

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/strategies');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.strategies && Array.isArray(data.strategies)) {
          setStrategies(data.strategies);
        }
      } catch (error) {
        console.warn('Failed to fetch strategies:', error);
      }
    };

    // Fetch immediately
    fetchStrategies();

    // Poll every 5 seconds
    const interval = setInterval(fetchStrategies, 5000);
    return () => clearInterval(interval);
  }, [setStrategies]);
}
