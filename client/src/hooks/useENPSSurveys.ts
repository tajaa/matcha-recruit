import { useState, useEffect } from 'react';
import { enpsApi } from '../api/xp';
import type { ENPSSurvey } from '../types/xp';

export function useENPSSurveys(status?: string) {
  const [data, setData] = useState<ENPSSurvey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const surveys = await enpsApi.getSurveys(status);
      setData(surveys);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch surveys');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [status]);

  return { data, loading, error, refetch: fetchData };
}
