import { useState, useCallback, useEffect, useRef } from 'react'
import {
  fetchLocations,
  fetchSummary,
  fetchAlerts,
  fetchPinnedRequirements,
  fetchJurisdictions,
  markAlertRead as apiMarkAlertRead,
  dismissAlert as apiDismissAlert,
  createLocation as apiCreateLocation,
  updateLocation as apiUpdateLocation,
  deleteLocation as apiDeleteLocation,
  pinRequirement as apiPinRequirement,
} from '../../api/compliance'
import type {
  BusinessLocation,
  ComplianceSummary,
  ComplianceAlert,
  PinnedRequirement,
  JurisdictionOption,
  LocationCreate,
  LocationUpdate,
} from '../../types/compliance'

export function useComplianceData(selectedLocationId?: string | null) {
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [summary, setSummary] = useState<ComplianceSummary | null>(null)
  const [alerts, setAlerts] = useState<ComplianceAlert[]>([])
  const [pinnedRequirements, setPinnedRequirements] = useState<PinnedRequirement[]>([])
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([])
  const [loading, setLoading] = useState(true)

  // Use ref so loadAlerts identity doesn't change on every location switch
  const locationRef = useRef(selectedLocationId)
  locationRef.current = selectedLocationId

  const loadLocations = useCallback(async () => {
    try { setLocations(await fetchLocations()) } catch { setLocations([]) }
  }, [])

  const loadSummary = useCallback(async () => {
    try { setSummary(await fetchSummary()) } catch { setSummary(null) }
  }, [])

  const loadAlerts = useCallback(async (status?: string) => {
    try { setAlerts(await fetchAlerts(status, undefined, locationRef.current ?? undefined)) } catch { setAlerts([]) }
  }, [])

  const loadPinnedRequirements = useCallback(async () => {
    try { setPinnedRequirements(await fetchPinnedRequirements()) } catch { setPinnedRequirements([]) }
  }, [])

  const loadJurisdictions = useCallback(async () => {
    try { setJurisdictions(await fetchJurisdictions()) } catch { setJurisdictions([]) }
  }, [])

  const refreshAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadLocations(), loadSummary(), loadAlerts('unread'), loadPinnedRequirements()])
    setLoading(false)
  }, [loadLocations, loadSummary, loadAlerts, loadPinnedRequirements])

  useEffect(() => { refreshAll() }, [refreshAll])

  // Reload alerts when selected location changes (without full page reload)
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    loadAlerts('unread')
  }, [selectedLocationId, loadAlerts])

  // Mutations
  const createLoc = useCallback(async (data: LocationCreate) => {
    const loc = await apiCreateLocation(data)
    await refreshAll()
    return loc
  }, [refreshAll])

  const updateLoc = useCallback(async (id: string, data: LocationUpdate) => {
    const loc = await apiUpdateLocation(id, data)
    await loadLocations()
    return loc
  }, [loadLocations])

  const deleteLoc = useCallback(async (id: string) => {
    await apiDeleteLocation(id)
    await refreshAll()
  }, [refreshAll])

  const markRead = useCallback(async (alertId: string) => {
    await apiMarkAlertRead(alertId)
    setAlerts((prev) => prev.filter((a) => a.id !== alertId))
    if (summary) setSummary({ ...summary, unread_alerts: Math.max(0, summary.unread_alerts - 1) })
  }, [summary])

  const dismiss = useCallback(async (alertId: string) => {
    await apiDismissAlert(alertId)
    setAlerts((prev) => prev.filter((a) => a.id !== alertId))
    if (summary) setSummary({ ...summary, unread_alerts: Math.max(0, summary.unread_alerts - 1) })
  }, [summary])

  const togglePin = useCallback(async (requirementId: string, isPinned: boolean) => {
    await apiPinRequirement(requirementId, isPinned)
    await loadPinnedRequirements()
  }, [loadPinnedRequirements])

  return {
    locations, summary, alerts, pinnedRequirements, jurisdictions, loading,
    loadLocations, loadSummary, loadAlerts, loadPinnedRequirements, loadJurisdictions, refreshAll,
    createLocation: createLoc, updateLocation: updateLoc, deleteLocation: deleteLoc,
    markAlertRead: markRead, dismissAlert: dismiss, togglePin,
  }
}
