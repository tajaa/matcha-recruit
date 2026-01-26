import { useState, useEffect } from 'react';
import { reviewsApi } from '../api/xp';
import type { ReviewCycle, ReviewTemplate } from '../types/xp';

export function useReviewTemplates() {
  const [data, setData] = useState<ReviewTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const templates = await reviewsApi.getTemplates();
      setData(templates);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch templates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return { data, loading, error, refetch: fetchData };
}

export function useReviewCycles() {
  const [data, setData] = useState<ReviewCycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const cycles = await reviewsApi.getCycles();
      setData(cycles);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch cycles');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return { data, loading, error, refetch: fetchData };
}
