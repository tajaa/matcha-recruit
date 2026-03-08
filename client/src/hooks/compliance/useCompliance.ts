import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { BusinessLocation, LocationCreate } from '../../api/compliance';
import { complianceAPI } from '../../api/compliance';

const ONE_HOUR = 1000 * 60 * 60;

export function useCompliance(companyId: string | null, selectedLocationId: string | null, isAdmin = false) {
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null);
  const [formData, setFormData] = useState<{
    name: string;
    address: string;
    city: string;
    state: string;
    county: string;
    zipcode: string;
    jurisdictionKey: string;
  }>({
    name: '',
    address: '',
    city: '',
    state: '',
    county: '',
    zipcode: '',
    jurisdictionKey: '',
  });
  const [useManualEntry, setUseManualEntry] = useState(false);
  const [mutationError, setMutationError] = useState<string | null>(null);

  // --- Card-level data: fetched on mount ---
  const { data: locations, isLoading: loadingLocations } = useQuery({
    queryKey: ['compliance-locations', companyId],
    queryFn: () => complianceAPI.getLocations(companyId || undefined),
    enabled: !isAdmin || !!companyId,
  });

  // --- Detail data: fetched only when a location is selected, cached 1hr ---
  const { data: requirements, isLoading: loadingRequirements } = useQuery({
    queryKey: ['compliance-requirements', selectedLocationId, companyId],
    queryFn: () => complianceAPI.getRequirements(selectedLocationId!, undefined, companyId || undefined),
    enabled: !!selectedLocationId,
    staleTime: ONE_HOUR,
    gcTime: ONE_HOUR,
  });

  const { data: alerts, isLoading: loadingAlerts } = useQuery({
    queryKey: ['compliance-alerts', selectedLocationId, companyId],
    queryFn: () => complianceAPI.getAlerts(undefined, companyId || undefined),
    enabled: !!selectedLocationId,
    staleTime: ONE_HOUR,
    gcTime: ONE_HOUR,
  });

  const { data: upcomingLegislation } = useQuery({
    queryKey: ['compliance-upcoming', selectedLocationId, companyId],
    queryFn: () => complianceAPI.getUpcomingLegislation(selectedLocationId!, companyId || undefined),
    enabled: !!selectedLocationId,
    staleTime: ONE_HOUR,
    gcTime: ONE_HOUR,
  });

  const { data: checkLog } = useQuery({
    queryKey: ['compliance-check-log', selectedLocationId, companyId],
    queryFn: () => complianceAPI.getCheckLog(selectedLocationId!, 20, companyId || undefined),
    enabled: !!selectedLocationId,
    staleTime: ONE_HOUR,
    gcTime: ONE_HOUR,
  });

  // Jurisdictions: only needed when add modal is open
  const { data: jurisdictions } = useQuery({
    queryKey: ['compliance-jurisdictions'],
    queryFn: complianceAPI.getJurisdictions,
    enabled: showAddModal,
    staleTime: ONE_HOUR,
    gcTime: ONE_HOUR,
  });

  // Mutations
  const createLocationMutation = useMutation({
    mutationFn: (data: LocationCreate) => complianceAPI.createLocation(data, companyId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
      setShowAddModal(false);
      setFormData({
        name: '',
        address: '',
        city: '',
        state: '',
        county: '',
        zipcode: '',
        jurisdictionKey: '',
      });
      setUseManualEntry(false);
    },
    onError: () => setMutationError('Failed to create location'),
  });

  const updateLocationMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: LocationCreate }) => complianceAPI.updateLocation(id, data, companyId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      setEditingLocation(null);
      setFormData({
        name: '',
        address: '',
        city: '',
        state: '',
        county: '',
        zipcode: '',
        jurisdictionKey: '',
      });
    },
    onError: () => setMutationError('Failed to update location'),
  });

  const deleteLocationMutation = useMutation({
    mutationFn: (id: string) => complianceAPI.deleteLocation(id, companyId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
    },
    onError: (err: Error) => setMutationError(err.message || 'Failed to delete location'),
  });

  const markAlertReadMutation = useMutation({
    mutationFn: (id: string) => complianceAPI.markAlertRead(id, companyId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-alerts', selectedLocationId, companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
    },
    onError: () => setMutationError('Failed to acknowledge alert'),
  });

  const dismissAlertMutation = useMutation({
    mutationFn: (id: string) => complianceAPI.dismissAlert(id, companyId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-alerts', selectedLocationId, companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
      queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
    },
    onError: () => setMutationError('Failed to dismiss alert'),
  });

  const handleSubmitLocation = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.city || !formData.state) return;

    const data: LocationCreate = {
      name: formData.name || undefined,
      address: formData.address || undefined,
      city: formData.city,
      state: formData.state,
      county: formData.county || undefined,
      zipcode: formData.zipcode || undefined,
    };

    if (editingLocation) {
      updateLocationMutation.mutate({ id: editingLocation.id, data });
    } else {
      createLocationMutation.mutate(data);
    }
  };

  const openEditModal = (location: BusinessLocation) => {
    setEditingLocation(location);
    setFormData({
      name: location.name || '',
      address: location.address || '',
      city: location.city,
      state: location.state,
      county: location.county || '',
      zipcode: location.zipcode,
      jurisdictionKey: `${location.city}|${location.state}|${location.county || ''}`,
    });
  };

  return {
    locations,
    loadingLocations,
    requirements,
    loadingRequirements,
    alerts,
    loadingAlerts,
    upcomingLegislation,
    checkLog,
    jurisdictions,
    showAddModal,
    setShowAddModal,
    editingLocation,
    setEditingLocation,
    formData,
    setFormData,
    useManualEntry,
    setUseManualEntry,
    mutationError,
    setMutationError,
    createLocationMutation,
    updateLocationMutation,
    deleteLocationMutation,
    markAlertReadMutation,
    dismissAlertMutation,
    handleSubmitLocation,
    openEditModal,
  };
}
