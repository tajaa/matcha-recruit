import type { PostalAddress } from '../../types'

const input = 'mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent'

/**
 * Controlled fields for a postal address. The server validates (a US address
 * needs a state and ZIP; no field may hold a card number); these only help.
 * `idPrefix` keeps labels unique when two address forms are on one page.
 */
export default function AddressFields({
  value, onChange, idPrefix,
}: { value: PostalAddress; onChange: (next: PostalAddress) => void; idPrefix: string }) {
  const set = (key: keyof PostalAddress) => (event: { target: { value: string } }) =>
    onChange({ ...value, [key]: event.target.value })
  const us = value.country.trim().toUpperCase() === 'US'
  return (
    <div className="grid gap-3 sm:grid-cols-6">
      <label htmlFor={`${idPrefix}-name`} className="block text-xs text-w-dim sm:col-span-6">
        Full name
        <input id={`${idPrefix}-name`} value={value.name} onChange={set('name')} autoComplete="name" required maxLength={80} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-line1`} className="block text-xs text-w-dim sm:col-span-4">
        Street address
        <input id={`${idPrefix}-line1`} value={value.line1} onChange={set('line1')} autoComplete="address-line1" required maxLength={120} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-line2`} className="block text-xs text-w-dim sm:col-span-2">
        Apt, suite (optional)
        <input id={`${idPrefix}-line2`} value={value.line2} onChange={set('line2')} autoComplete="address-line2" maxLength={120} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-city`} className="block text-xs text-w-dim sm:col-span-3">
        City
        <input id={`${idPrefix}-city`} value={value.city} onChange={set('city')} autoComplete="address-level2" required maxLength={80} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-region`} className="block text-xs text-w-dim sm:col-span-1">
        {us ? 'State' : 'Region'}
        <input id={`${idPrefix}-region`} value={value.region} onChange={set('region')} autoComplete="address-level1" required={us} maxLength={80} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-postal`} className="block text-xs text-w-dim sm:col-span-2">
        {us ? 'ZIP' : 'Postal code'}
        <input id={`${idPrefix}-postal`} value={value.postal_code} onChange={set('postal_code')} autoComplete="postal-code" required maxLength={20} className={input} />
      </label>
      <label htmlFor={`${idPrefix}-country`} className="block text-xs text-w-dim sm:col-span-2">
        Country code
        <input
          id={`${idPrefix}-country`} value={value.country} onChange={set('country')} autoComplete="country"
          required maxLength={2} placeholder="US" className={`${input} uppercase`}
        />
      </label>
      <label htmlFor={`${idPrefix}-phone`} className="block text-xs text-w-dim sm:col-span-4">
        Phone (optional, for delivery)
        <input id={`${idPrefix}-phone`} type="tel" value={value.phone} onChange={set('phone')} autoComplete="tel" maxLength={30} className={input} />
      </label>
    </div>
  )
}
