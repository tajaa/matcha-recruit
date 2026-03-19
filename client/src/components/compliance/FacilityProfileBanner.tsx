import { useRef, useState } from 'react'
import { Button } from '../ui'
import { updateFacilityAttributes } from '../../api/compliance'
import type { FacilityAttributes } from '../../types/compliance'

const ENTITY_TYPES = [
  { value: 'fqhc', label: 'Federally Qualified Health Center (FQHC)' },
  { value: 'hospital', label: 'Hospital' },
  { value: 'critical_access_hospital', label: 'Critical Access Hospital' },
  { value: 'clinic', label: 'Clinic / Outpatient' },
  { value: 'nursing_facility', label: 'Nursing Facility' },
  { value: 'pharmacy', label: 'Pharmacy' },
  { value: 'dental', label: 'Dental Practice' },
  { value: 'behavioral_health', label: 'Behavioral Health' },
  { value: 'ambulatory_surgery_center', label: 'Ambulatory Surgery Center' },
  { value: 'home_health', label: 'Home Health' },
  { value: 'hospice', label: 'Hospice' },
  { value: 'dialysis_center', label: 'Dialysis Center' },
  { value: 'lab', label: 'Laboratory' },
  { value: 'other', label: 'Other Healthcare' },
]

const PAYER_OPTIONS = [
  { value: 'medicare', label: 'Medicare' },
  { value: 'medi_cal', label: 'Medi-Cal (CA Medicaid)' },
  { value: 'medicaid_other', label: 'Medicaid (other states)' },
  { value: 'commercial', label: 'Commercial Insurance' },
  { value: 'tricare', label: 'TRICARE' },
]

function getEntityLabel(value: string): string {
  return ENTITY_TYPES.find((t) => t.value === value)?.label || value.replace(/_/g, ' ')
}

function getPayerLabels(contracts: string[]): string {
  return contracts
    .map((v) => PAYER_OPTIONS.find((p) => p.value === v)?.label || v)
    .join(', ')
}

function getDismissKey(locationId: string): string {
  return `facility_profile_dismissed_${locationId}`
}

type LocationSummary = {
  id: string
  facility_attributes?: FacilityAttributes | null
}

type Props = {
  locationId: string
  facilityAttributes: FacilityAttributes | null | undefined
  onUpdated: (attrs: FacilityAttributes) => void
  /** All company locations — used to offer "apply to all" */
  allLocations?: LocationSummary[]
  /** Location source — hide banner for employee-derived locations */
  source?: 'manual' | 'employee_derived'
}

export function FacilityProfileBanner({ locationId, facilityAttributes, onUpdated, allLocations, source }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [entityType, setEntityType] = useState(facilityAttributes?.entity_type || '')
  const [payers, setPayers] = useState<string[]>(facilityAttributes?.payer_contracts || [])
  const [applyToAll, setApplyToAll] = useState(false)
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(getDismissKey(locationId)) === 'true'
  )

  // Reset state when locationId changes (component may not remount)
  const prevLocationRef = useRef(locationId)
  if (prevLocationRef.current !== locationId) {
    prevLocationRef.current = locationId
    setExpanded(false)
    setSaving(false)
    setSaveError(null)
    setEntityType(facilityAttributes?.entity_type || '')
    setPayers(facilityAttributes?.payer_contracts || [])
    setApplyToAll(false)
    setDismissed(localStorage.getItem(getDismissKey(locationId)) === 'true')
  }

  const hasAttrs = facilityAttributes &&
    (facilityAttributes.entity_type || (facilityAttributes.payer_contracts && facilityAttributes.payer_contracts.length > 0))

  // Hide for employee-derived locations or dismissed
  if (source === 'employee_derived') return null
  if (dismissed) return null

  function togglePayer(value: string) {
    setPayers((prev) =>
      prev.includes(value) ? prev.filter((p) => p !== value) : [...prev, value]
    )
  }

  function handleDismiss() {
    localStorage.setItem(getDismissKey(locationId), 'true')
    setDismissed(true)
  }

  // Locations that don't have a facility profile yet (excluding current)
  const otherUnprofiled = (allLocations || []).filter(
    (l) => l.id !== locationId && !(l.facility_attributes?.entity_type)
  )

  async function handleSave() {
    if (!entityType) return
    setSaving(true)
    setSaveError(null)
    try {
      const data: Partial<FacilityAttributes> = {
        entity_type: entityType,
        payer_contracts: payers.length > 0 ? payers : undefined,
      }
      const result = await updateFacilityAttributes(locationId, data)

      // Apply to other locations without a profile
      if (applyToAll && otherUnprofiled.length > 0) {
        await Promise.all(
          otherUnprofiled.map((l) =>
            updateFacilityAttributes(l.id, data).then(() => {
              localStorage.setItem(getDismissKey(l.id), 'true')
            })
          )
        )
      }

      onUpdated(result.facility_attributes)
      setExpanded(false)
      localStorage.setItem(getDismissKey(locationId), 'true')
      setDismissed(true)
    } catch {
      setSaveError('Failed to save facility profile. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  // Inferred profile view: show detected attributes with confirm/edit options
  if (hasAttrs && !expanded) {
    const entityLabel = getEntityLabel(facilityAttributes.entity_type || '')
    const payerLabel = facilityAttributes.payer_contracts?.length
      ? getPayerLabels(facilityAttributes.payer_contracts)
      : null

    return (
      <div className="mb-3 border border-emerald-800/40 rounded-lg bg-emerald-950/20">
        <div className="flex items-center justify-between px-3 py-2.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-emerald-400 text-sm shrink-0">&#10003;</span>
            <p className="text-sm text-emerald-300/90 truncate">
              Detected: {entityLabel}
              {payerLabel ? ` | ${payerLabel}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Button variant="ghost" size="sm" onClick={() => {
              setEntityType(facilityAttributes.entity_type || '')
              setPayers(facilityAttributes.payer_contracts || [])
              setExpanded(true)
            }}>
              Edit
            </Button>
            <Button variant="ghost" size="sm" onClick={handleDismiss}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // No attrs set: prompt to set up
  // Or expanded from inferred view: show edit form
  return (
    <div className="mb-3 border border-cyan-800/40 rounded-lg bg-cyan-950/20">
      {!expanded && (
        <div className="flex items-center justify-between px-3 py-2.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-cyan-400 text-sm shrink-0">+</span>
            <p className="text-sm text-cyan-300/90 truncate">
              Set up facility profile for more accurate healthcare compliance
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
            Set Up
          </Button>
        </div>
      )}

      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-cyan-800/30 pt-3">
          <div className="flex items-center justify-between">
            <label className="block text-xs font-medium text-zinc-400">Facility Type</label>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              Close
            </button>
          </div>
          <select
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none"
          >
            <option value="">Select facility type...</option>
            {ENTITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Payer Contracts</label>
            <div className="flex flex-wrap gap-2">
              {PAYER_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => togglePayer(p.value)}
                  className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                    payers.includes(p.value)
                      ? 'bg-cyan-900/40 border-cyan-700/60 text-cyan-300'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {saveError && (
            <p className="text-xs text-red-400">{saveError}</p>
          )}

          {otherUnprofiled.length > 0 && (
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(e) => setApplyToAll(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-900 text-cyan-500 focus:ring-cyan-500/30"
              />
              <span className="text-xs text-zinc-400">
                Apply to all {otherUnprofiled.length} other location{otherUnprofiled.length > 1 ? 's' : ''} without a profile
              </span>
            </label>
          )}

          <div className="flex items-center justify-between pt-1">
            <p className="text-[11px] text-zinc-600">
              Triggers additional compliance checks for your facility type and payers
            </p>
            <Button size="sm" onClick={handleSave} disabled={saving || !entityType}>
              {saving ? 'Saving...' : applyToAll ? `Save & Apply to ${otherUnprofiled.length + 1} Locations` : 'Save Profile'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
