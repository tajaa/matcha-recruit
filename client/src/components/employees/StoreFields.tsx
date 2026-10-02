import { US_STATES } from '../../hooks/compliance/useJurisdictionSearch'
import { TIMEZONE_OPTIONS } from '../../utils/locationTimezone'
import { Input, Select } from '../ui'
import { withStoreChange, type StoreForm } from './storeForm'

interface StoreFieldsProps {
  value: StoreForm
  onChange: (next: StoreForm) => void
  /** Render dropdowns in a portal — set inside a scrolling modal body. */
  portal?: boolean
}

/** The store form's fields, shared by setup and the schedule's own store
 *  dialog. Rules and defaults live in `storeForm.ts`. */
export function StoreFields({ value, onChange, portal }: StoreFieldsProps) {
  const set = (change: Partial<StoreForm>) => onChange(withStoreChange(value, change))
  return (
    <div className="space-y-3">
      <Input label="Store name" required maxLength={255} value={value.name}
        onChange={(event) => set({ name: event.target.value })} placeholder="e.g. Downtown" />
      <Input label="Street address" required maxLength={500} value={value.address}
        onChange={(event) => set({ address: event.target.value })} placeholder="e.g. 120 Main St" />
      <div className="grid gap-3 sm:grid-cols-[1fr_180px_120px]">
        <Input label="City" required maxLength={100} value={value.city}
          onChange={(event) => set({ city: event.target.value })} />
        <Select label="State" required portal={portal} options={US_STATES} value={value.state}
          onChange={(event) => set({ state: event.target.value })} placeholder="State" />
        <Input label="Zip code" required inputMode="numeric" maxLength={10} value={value.zipcode}
          onChange={(event) => set({ zipcode: event.target.value })} />
      </div>
      <Select label="Time zone" required portal={portal} options={TIMEZONE_OPTIONS} value={value.timezone}
        onChange={(event) => set({ timezone: event.target.value })} placeholder="Select a time zone" />
    </div>
  )
}
