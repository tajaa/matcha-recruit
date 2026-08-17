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
}

export default function LocationPicker({
  locations, value, onChange, allowAll = false,
  allLabel = 'All locations', placeholder = 'Select a location…', className,
}: LocationPickerProps) {
  return (
    <label className={`inline-flex items-center gap-1.5 text-xs text-zinc-500 ${className ?? ''}`}>
      <MapPin className="h-3.5 w-3.5" />
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
      >
        {allowAll ? <option value="">{allLabel}</option> : <option value="" disabled>{placeholder}</option>}
        {locations.map((location) => (
          <option key={location.id} value={location.id} disabled={!location.is_active}>
            {locationLabel(location)}
          </option>
        ))}
      </select>
    </label>
  )
}
