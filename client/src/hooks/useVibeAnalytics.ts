import { useState, useEffect } from 'react';
import { vibeChecksApi } from '../api/xp';
import type { VibeAnalytics } from '../types/xp';

export function useVibeAnalytics(period: string, managerId?: string) {
  const [data, setData] = useState<VibeAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const analytics = await vibeChecksApi.getAnalytics(period, managerId);
        setData(analytics);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [period, managerId]);

  return { data, loading, error, refetch: () => {
    setLoading(true);
    vibeChecksApi.getAnalytics(period, managerId)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to fetch analytics'))
      .finally(() => setLoading(false));
  }};
}
