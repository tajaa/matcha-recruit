import { MapPin } from 'lucide-react'
import { locationLabel, type CompanyLocation } from '../../hooks/useLocationScope'

interface LocationPickerProps {
  locations: CompanyLocation[]
  value: string
  onChange(id: string): void
  /** When true, the empty option is a real "everything" selection instead of
   *  a disabled placeholder. Off for scheduling (scope must never clear back
   *  to "everything" — the server won't serve it), on for pages like
   *  /app/employees that legitimately default to the whole company. */
  allowAll?: boolean
  allLabel?: string
  placeholder?: string
  className?: string
  /** Options read by store name only (the full address stays in the tooltip),
   *  for a toolbar where a whole address crowds out everything beside it. */
  compact?: boolean
}

export default function LocationPicker({
  locations, value, onChange, allowAll = false,
  allLabel = 'All locations', placeholder = 'Select a location…', className, compact = false,
}: LocationPickerProps) {
  const selected = locations.find((location) => location.id === value)
  const optionLabel = (location: CompanyLocation) => (compact && location.name
    ? `${location.name}${location.is_active ? '' : ' (inactive)'}`
    : locationLabel(location))
  return (
    <label className={`inline-flex min-w-0 items-center gap-1.5 text-xs text-zinc-500 ${className ?? ''}`}>
      <MapPin className="h-3.5 w-3.5" />
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        title={selected ? locationLabel(selected) : undefined}
        aria-label="Location"
        // compact: fills a phone toolbar row, and 16px text there keeps iOS from zooming on focus.
        className={`truncate rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-zinc-200 outline-none focus:border-zinc-500 ${compact ? 'w-full min-w-0 text-base sm:w-auto sm:max-w-[16rem] sm:text-xs' : 'max-w-[16rem] text-xs'}`}
      >
        {allowAll ? <option value="">{allLabel}</option> : <option value="" disabled>{placeholder}</option>}
        {locations.map((location) => (
          <option key={location.id} value={location.id} disabled={!location.is_active}>
            {optionLabel(location)}
          </option>
        ))}
      </select>
    </label>
  )
}
