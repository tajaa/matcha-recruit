import { inferLocationTimezone } from '../../utils/locationTimezone'

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
