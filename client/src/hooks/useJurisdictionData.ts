import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function useJurisdictionData() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['jurisdiction-data-overview'],
    queryFn: () => api.adminJurisdictionData.overview(),
    staleTime: 1000 * 60 * 30,
  });

  return { data, isLoading, error, refetch };
}
