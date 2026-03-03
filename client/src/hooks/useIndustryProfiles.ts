import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { IndustryProfileCreate, IndustryProfileUpdate } from '../api/client';

const KEY = ['industry-profiles'];

export function useIndustryProfiles() {
  const queryClient = useQueryClient();

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api.adminIndustryProfiles.list(),
    staleTime: 1000 * 60 * 60,
  });

  const createMutation = useMutation({
    mutationFn: (data: IndustryProfileCreate) => api.adminIndustryProfiles.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: IndustryProfileUpdate }) =>
      api.adminIndustryProfiles.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.adminIndustryProfiles.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  return {
    profiles,
    isLoading,
    create: createMutation.mutateAsync,
    update: updateMutation.mutateAsync,
    remove: deleteMutation.mutateAsync,
  };
}
