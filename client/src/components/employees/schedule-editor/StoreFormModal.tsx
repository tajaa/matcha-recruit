import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { createScheduleStore, updateScheduleStore } from '../../../api/employees/scheduleStores'
import type { CompanyLocation } from '../../../hooks/useLocationScope'
import { errorMessage, type ScheduleStore } from '../../../types/employeeSchedule'
import { inferLocationTimezone } from '../../../utils/locationTimezone'
import { Button, Modal } from '../../ui'
import { EMPTY_STORE, StoreFields, storeFormError, type StoreForm } from '../StoreFields'

interface StoreFormModalProps {
  open: boolean
  /** The store being fixed or edited; null adds a new one. */
  store: CompanyLocation | null
  /** Why the store cannot publish yet — shown above the form when editing. */
  notice?: string | null
  onClose(): void
  onSaved(store: ScheduleStore): void
}

function formFor(store: CompanyLocation | null): StoreForm {
  if (!store) return EMPTY_STORE
  const state = store.state ?? ''
  return {
    name: store.name ?? '',
    address: store.address ?? '',
    city: store.city ?? '',
    state,
    zipcode: store.zipcode ?? '',
    // A store with no time zone is the usual reason this form is open: start
    // from the one its state implies rather than from an empty dropdown.
    timezone: store.timezone || inferLocationTimezone(state) || '',
  }
}

/** Add a store, or fill in what an existing one is missing, without leaving
 *  the schedule. Only the fields publishing needs — no EIN, NAICS or headcount. */
export default function StoreFormModal({ open, store, notice, onClose, onSaved }: StoreFormModalProps) {
  const [form, setForm] = useState<StoreForm>(EMPTY_STORE)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setForm(formFor(store))
    setError(null)
  }, [open, store])

  async function save() {
    const problem = storeFormError(form)
    if (problem) { setError(problem); return }
    const payload = {
      name: form.name.trim(),
      address: form.address.trim(),
      city: form.city.trim(),
      state: form.state,
      zipcode: form.zipcode.trim(),
      timezone: form.timezone,
    }
    setSaving(true)
    setError(null)
    try {
      onSaved(store ? await updateScheduleStore(store.id, payload) : await createScheduleStore(payload))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={store ? 'Store details' : 'Add a store'} dismissible={!saving}>
      {/* noValidate: the form names what is wrong itself ("Choose the time
          zone — this state has more than one"), which the browser's generic
          "fill out this field" bubble cannot. */}
      <form
        noValidate
        className="space-y-4"
        onSubmit={(event) => { event.preventDefault(); void save() }}
      >
        {notice && (
          <p className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">{notice}</p>
        )}
        {!store && (
          <p className="text-sm text-zinc-400">A store gets its own schedule. Its address and time zone are what let you publish a week.</p>
        )}
        <StoreFields value={form} onChange={setForm} portal />
        {error && <p role="alert" className="rounded border border-red-900/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" disabled={saving} onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}{store ? 'Save store' : 'Add store'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
