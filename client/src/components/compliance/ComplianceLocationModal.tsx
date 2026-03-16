import { useState, useEffect } from 'react'
import { Button, Input, Modal, Select } from '../ui'
import { useJurisdictionSearch, US_STATES } from '../../hooks/compliance/useJurisdictionSearch'
import type { BusinessLocation, JurisdictionOption, LocationCreate } from '../../types/compliance'

type Props = {
  open: boolean
  onClose: () => void
  editingLocation: BusinessLocation | null
  jurisdictions: JurisdictionOption[]
  onSubmit: (data: LocationCreate, editId?: string) => void
  saving: boolean
}

const EMPTY = { name: '', address: '', city: '', state: '', county: '', zipcode: '' }

export function ComplianceLocationModal({ open, onClose, editingLocation, jurisdictions, onSubmit, saving }: Props) {
  const [form, setForm] = useState(EMPTY)
  const [useManual, setUseManual] = useState(false)
  const [selectedKey, setSelectedKey] = useState('')
  const { jurisdictionSearch, setJurisdictionSearch, filteredJurisdictions } = useJurisdictionSearch(jurisdictions)

  useEffect(() => {
    if (editingLocation) {
      setForm({
        name: editingLocation.name || '',
        address: editingLocation.address || '',
        city: editingLocation.city,
        state: editingLocation.state,
        county: editingLocation.county || '',
        zipcode: editingLocation.zipcode || '',
      })
      setUseManual(true)
    } else {
      setForm(EMPTY)
      setUseManual(false)
      setSelectedKey('')
      setJurisdictionSearch('')
    }
  }, [editingLocation, open, setJurisdictionSearch])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.city || !form.state) return
    const data: LocationCreate = {
      name: form.name || undefined,
      address: form.address || undefined,
      city: form.city,
      state: form.state,
      county: form.county || undefined,
      zipcode: form.zipcode || undefined,
    }
    onSubmit(data, editingLocation?.id)
  }

  function selectJurisdiction(j: JurisdictionOption) {
    const key = `${j.city}|${j.state}|${j.county || ''}`
    setSelectedKey(key)
    setForm((f) => ({ ...f, city: j.city, state: j.state, county: j.county || '' }))
  }

  const showPicker = !editingLocation && !useManual && jurisdictions.length > 0

  return (
    <Modal open={open} onClose={onClose} title={editingLocation ? 'Edit Location' : 'Add Location'}>
      <form onSubmit={handleSubmit} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        <Input label="Name (optional)" value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. HQ Office" />

        {showPicker ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Select Jurisdiction</p>
              <button type="button" onClick={() => setUseManual(true)}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Manual Entry</button>
            </div>
            <Input label="" placeholder="Search cities..." value={jurisdictionSearch}
              onChange={(e) => setJurisdictionSearch(e.target.value)} />
            <div className="max-h-40 overflow-y-auto border border-zinc-800 rounded-lg">
              {Object.keys(filteredJurisdictions).length === 0 ? (
                <p className="px-4 py-4 text-xs text-zinc-600 text-center">
                  {jurisdictionSearch ? 'No matches' : 'Loading jurisdictions...'}
                </p>
              ) : (
                Object.entries(filteredJurisdictions).map(([state, items]) => {
                  const stateLabel = US_STATES.find((s) => s.value === state)?.label || state
                  return (
                    <div key={state}>
                      <div className="px-3 py-1.5 bg-zinc-900/60 text-[11px] text-zinc-500 uppercase tracking-wide sticky top-0">{stateLabel}</div>
                      {items.map((j) => {
                        const key = `${j.city}|${j.state}|${j.county || ''}`
                        return (
                          <button key={key} type="button" onClick={() => selectJurisdiction(j)}
                            className={`w-full text-left px-3 py-2 text-sm transition-colors border-b border-zinc-800/40 last:border-0 ${
                              selectedKey === key ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/30 hover:text-zinc-200'
                            }`}>
                            {j.city}, {j.state}
                            {j.has_local_ordinance && (
                              <span className="ml-2 text-[10px] text-emerald-400">Local Ordinance</span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  )
                })
              )}
            </div>
            {selectedKey && (
              <p className="text-xs text-zinc-400">Selected: <span className="text-zinc-200">{form.city}, {form.state}</span>
                {form.county && <span className="text-zinc-500 ml-1">({form.county} County)</span>}
              </p>
            )}
          </div>
        ) : (
          <>
            {!editingLocation && jurisdictions.length > 0 && (
              <button type="button" onClick={() => { setUseManual(false); setForm(EMPTY); setSelectedKey('') }}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Use Jurisdiction Picker</button>
            )}
            <Input label="Address" value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Street address" />
            <div className="grid grid-cols-2 gap-3">
              <Input label="City" required value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })} />
              <Select label="State" required
                options={[{ value: '', label: '--' }, ...US_STATES.map((s) => ({ value: s.value, label: `${s.value} - ${s.label}` }))]}
                value={form.state}
                onChange={(e) => setForm({ ...form, state: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input label="County" value={form.county}
                onChange={(e) => setForm({ ...form, county: e.target.value })} />
              <Input label="ZIP Code" value={form.zipcode}
                onChange={(e) => setForm({ ...form, zipcode: e.target.value })} maxLength={10} />
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving || (!form.city || !form.state)}>
            {saving ? 'Saving...' : editingLocation ? 'Update Location' : 'Add Location'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
