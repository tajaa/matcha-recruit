import { US_STATES } from '../../hooks/compliance/useJurisdictionSearch'
import { inferLocationTimezone, TIMEZONE_OPTIONS } from '../../utils/locationTimezone'
import { Input, Select } from '../ui'

/** What scheduling needs to know about a store — and all of it is required:
 *  a week cannot be published for a store missing its address or time zone. */
export type StoreForm = {
  name: string
  address: string
  city: string
  state: string
  zipcode: string
  timezone: string
}

export const EMPTY_STORE: StoreForm = {
  name: '', address: '', city: '', state: '', zipcode: '', timezone: '',
}

const ZIPCODE = /^\d{5}(-\d{4})?$/

/** The first thing wrong with a store form, in the order the fields appear. */
export function storeFormError(form: StoreForm): string | null {
  if (!form.name.trim()) return 'Give the store a name.'
  if (!form.address.trim()) return 'Enter the street address.'
  if (!form.city.trim()) return 'Enter the city.'
  if (!form.state) return 'Choose the state.'
  if (!ZIPCODE.test(form.zipcode.trim())) return 'Zip code must look like 12345 or 12345-6789.'
  if (!form.timezone) return 'Choose the time zone — this state has more than one.'
  return null
}

/** Applies a field change, keeping the time zone in step with the state until
 *  the manager picks one themselves. */
export function withStoreChange(form: StoreForm, change: Partial<StoreForm>): StoreForm {
  const next = { ...form, ...change }
  if (change.state !== undefined && change.state !== form.state) {
    const followedState = !form.timezone || form.timezone === inferLocationTimezone(form.state)
    if (followedState) next.timezone = inferLocationTimezone(change.state) ?? ''
  }
  return next
}

interface StoreFieldsProps {
  value: StoreForm
  onChange: (next: StoreForm) => void
  /** Render dropdowns in a portal — set inside a scrolling modal body. */
  portal?: boolean
}

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
