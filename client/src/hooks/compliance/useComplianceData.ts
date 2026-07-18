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
} from '../../api/compliance/compliance'
import type {
  BusinessLocation,
  ComplianceSummary,
  ComplianceAlert,
  PinnedRequirement,
  JurisdictionOption,
  LocationCreate,
  LocationUpdate,
} from '../../types/compliance'

// `lite` = Matcha-X read-only taste (compliance_lite). Skips the Pro-only
// alerts + pinned-requirements fetches (their endpoints stay `compliance`-gated
// and would 403). The try/catch swallows the 403 either way; this just avoids
// the noise and the wasted round-trips.
export function useComplianceData(selectedLocationId?: string | null, lite = false) {
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [summary, setSummary] = useState<ComplianceSummary | null>(null)
  const [alerts, setAlerts] = useState<ComplianceAlert[]>([])
  const [pinnedRequirements, setPinnedRequirements] = useState<PinnedRequirement[]>([])
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([])
  const [loading, setLoading] = useState(true)

  // Use ref so loadAlerts identity doesn't change on every location switch
  const locationRef = useRef(selectedLocationId)
  locationRef.current = selectedLocationId

  // Per-loader request ids drop stale responses (e.g. rapid location switches
  // reordering loadAlerts). Each source needs its own id because refreshAll
  // fires them concurrently.
  const locReq = useRef(0)
  const sumReq = useRef(0)
  const alertReq = useRef(0)
  const pinReq = useRef(0)
  const jurReq = useRef(0)

  const loadLocations = useCallback(async () => {
    const id = ++locReq.current
    try { const d = await fetchLocations(); if (id === locReq.current) setLocations(d) } catch { if (id === locReq.current) setLocations([]) }
  }, [])

  const loadSummary = useCallback(async () => {
    const id = ++sumReq.current
    try { const d = await fetchSummary(); if (id === sumReq.current) setSummary(d) } catch { if (id === sumReq.current) setSummary(null) }
  }, [])

  const loadAlerts = useCallback(async (status?: string) => {
    const id = ++alertReq.current
    try { const d = await fetchAlerts(status, undefined, locationRef.current ?? undefined); if (id === alertReq.current) setAlerts(d) } catch { if (id === alertReq.current) setAlerts([]) }
  }, [])

  const loadPinnedRequirements = useCallback(async () => {
    const id = ++pinReq.current
    try { const d = await fetchPinnedRequirements(); if (id === pinReq.current) setPinnedRequirements(d) } catch { if (id === pinReq.current) setPinnedRequirements([]) }
  }, [])

  const loadJurisdictions = useCallback(async () => {
    const id = ++jurReq.current
    try { const d = await fetchJurisdictions(); if (id === jurReq.current) setJurisdictions(d) } catch { if (id === jurReq.current) setJurisdictions([]) }
  }, [])

  const refreshAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([
      loadLocations(),
      loadSummary(),
      ...(lite ? [] : [loadAlerts('unread'), loadPinnedRequirements()]),
    ])
    setLoading(false)
  }, [lite, loadLocations, loadSummary, loadAlerts, loadPinnedRequirements])

  useEffect(() => { refreshAll() }, [refreshAll])

  // Reload alerts when selected location changes (without full page reload)
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    if (!lite) loadAlerts('unread')
  }, [selectedLocationId, lite, loadAlerts])

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
