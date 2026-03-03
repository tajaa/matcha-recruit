import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { api } from '../api/client';

export function useJurisdictionData() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['jurisdiction-data-overview'],
    queryFn: () => api.adminJurisdictionData.overview(),
    staleTime: 1000 * 60 * 30,
  });

  const hardRefresh = useCallback(async () => {
    const fresh = await api.adminJurisdictionData.overview(true);
    queryClient.setQueryData(['jurisdiction-data-overview'], fresh);
  }, [queryClient]);

  return { data, isLoading, error, refetch, hardRefresh };
}
