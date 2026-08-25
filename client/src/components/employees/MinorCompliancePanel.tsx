import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Input, Select } from '../ui'
import { api } from '../../api/client'
import { locationLabel, type CompanyLocation } from '../../hooks/useLocationScope'

type MinorStatus = 'minor' | 'adult' | 'unknown'

type WorkPermit = {
  id: string
  location_id: string | null
  location_name: string | null
  issued_at: string | null
  expires_at: string
  status: 'active' | 'superseded'
  confirmed_on_file: boolean
  validity: 'valid' | 'expiring' | 'expired' | 'inactive'
}

const STATUS_VARIANT: Record<MinorStatus, 'success' | 'warning' | 'neutral'> = {
  minor: 'warning',
  adult: 'success',
  unknown: 'neutral',
}

const PERMIT_VARIANT: Record<WorkPermit['validity'], 'success' | 'warning' | 'danger' | 'neutral'> = {
  valid: 'success',
  expiring: 'warning',
  expired: 'danger',
  inactive: 'neutral',
}

export function MinorCompliancePanel({
  employeeId,
  minorStatus,
  dateOfBirthOnFile,
  workLocationId,
  locations,
  onUpdated,
}: {
  employeeId: string
  minorStatus: MinorStatus
  dateOfBirthOnFile: boolean
  workLocationId: string | null
  locations: CompanyLocation[]
  onUpdated: () => void
}) {
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [savingDob, setSavingDob] = useState(false)
  const [dobError, setDobError] = useState('')
  const [permits, setPermits] = useState<WorkPermit[]>([])
  const [permitsLoading, setPermitsLoading] = useState(false)
  const [permitError, setPermitError] = useState('')
  const [locationId, setLocationId] = useState(workLocationId ?? '')
  const [issuedAt, setIssuedAt] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [savingPermit, setSavingPermit] = useState(false)
  const effectiveLocationId = locationId || workLocationId || locations[0]?.id || ''

  const loadPermits = useCallback(async () => {
    setPermitsLoading(true)
    try {
      const result = await api.get<{ permits: WorkPermit[] }>(`/employees/${employeeId}/work-permits`)
      setPermits(result.permits)
    } catch (error) {
      setPermitError(error instanceof Error ? error.message : 'Could not load work permits')
    } finally {
      setPermitsLoading(false)
    }
  }, [employeeId])

  useEffect(() => {
    if (minorStatus === 'minor') void loadPermits()
  }, [loadPermits, minorStatus])

  async function saveDateOfBirth() {
    if (!dateOfBirth) return
    setSavingDob(true)
    setDobError('')
    try {
      await api.put(`/employees/${employeeId}/demographics/date-of-birth`, { date_of_birth: dateOfBirth })
      setDateOfBirth('')
      onUpdated()
    } catch (error) {
      setDobError(error instanceof Error ? error.message : 'Could not save birth date')
    } finally {
      setSavingDob(false)
    }
  }

  async function savePermit() {
    if (!effectiveLocationId || !expiresAt) return
    setSavingPermit(true)
    setPermitError('')
    try {
      await api.post(`/employees/${employeeId}/work-permits`, {
        location_id: effectiveLocationId,
        issued_at: issuedAt || null,
        expires_at: expiresAt,
        confirmed_on_file: true,
      })
      setIssuedAt('')
      setExpiresAt('')
      await loadPermits()
    } catch (error) {
      setPermitError(error instanceof Error ? error.message : 'Could not save work permit')
    } finally {
      setSavingPermit(false)
    }
  }

  return (
    <section className="mt-6 border-t border-zinc-800 pt-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Minor Compliance</h3>
          <p className="mt-1 text-xs text-zinc-500">Birth date is stored privately; this profile shows only the derived compliance status.</p>
        </div>
        <Badge variant={STATUS_VARIANT[minorStatus]}>{minorStatus === 'unknown' ? 'Age unknown' : minorStatus === 'minor' ? 'Minor' : 'Adult'}</Badge>
      </div>

      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-52 flex-1">
            <Input
              label={dateOfBirthOnFile ? 'Replace birth date' : 'Birth date'}
              type="date"
              value={dateOfBirth}
              onChange={(event) => setDateOfBirth(event.target.value)}
            />
          </div>
          <Button size="sm" onClick={saveDateOfBirth} disabled={!dateOfBirth || savingDob}>
            {savingDob ? 'Saving...' : dateOfBirthOnFile ? 'Replace date' : 'Save date'}
          </Button>
        </div>
        {dateOfBirthOnFile && <p className="mt-2 text-xs text-zinc-500">A birth date is already on file. Enter a new value only to correct it.</p>}
        {dobError && <p className="mt-2 text-xs text-red-400">{dobError}</p>}
      </div>

      {minorStatus === 'minor' && (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-medium text-zinc-200">Work permits</h4>
              <p className="mt-1 text-xs text-zinc-500">A confirmed, current permit is required at the assigned location.</p>
            </div>
            {permitsLoading && <span className="text-xs text-zinc-500">Loading...</span>}
          </div>

          {permits.map((permit) => (
            <div key={permit.id} className="mt-3 flex items-center justify-between gap-3 border-t border-zinc-800 pt-3 text-sm">
              <div>
                <p className="text-zinc-200">{permit.location_name || locations.find((location) => location.id === permit.location_id)?.name || 'Work location'}</p>
                <p className="text-xs text-zinc-500">
                  {permit.issued_at ? `Issued ${new Date(permit.issued_at).toLocaleDateString()} · ` : ''}
                  Expires {new Date(permit.expires_at).toLocaleDateString()}
                </p>
              </div>
              <Badge variant={PERMIT_VARIANT[permit.validity]}>{permit.validity}</Badge>
            </div>
          ))}
          {!permitsLoading && permits.length === 0 && <p className="mt-3 text-sm text-amber-300">No confirmed work permit is on file. Scheduling is blocked until one is recorded.</p>}

          <div className="mt-4 grid grid-cols-1 gap-3 border-t border-zinc-800 pt-4 sm:grid-cols-3">
            <Select
              label="Permit location"
              options={locations.map((location) => ({ value: location.id, label: locationLabel(location) }))}
              placeholder="— Select —"
              value={effectiveLocationId}
              onChange={(event) => setLocationId(event.target.value)}
            />
            <Input label="Issued" type="date" value={issuedAt} onChange={(event) => setIssuedAt(event.target.value)} />
            <Input label="Expires" type="date" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
          </div>
          <div className="mt-3 flex items-center justify-between gap-3">
            {permitError && <p className="text-xs text-red-400">{permitError}</p>}
            <Button className="ml-auto" size="sm" onClick={savePermit} disabled={!effectiveLocationId || !expiresAt || savingPermit}>
              {savingPermit ? 'Recording...' : 'Confirm permit on file'}
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
