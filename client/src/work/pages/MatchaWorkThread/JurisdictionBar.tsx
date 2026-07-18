import { MapPin } from 'lucide-react'
import type { BusinessLocation } from '../../../types/compliance'
import type { ThreadTheme } from './theme'

interface JurisdictionBarProps {
  complianceMode: boolean
  locationsUnavailable: boolean
  locations: BusinessLocation[]
  th: ThreadTheme
}

// Jurisdiction bar — shows when compliance mode is on
export default function JurisdictionBar({ complianceMode, locationsUnavailable, locations, th }: JurisdictionBarProps) {
  return (
    <>
      {complianceMode && locationsUnavailable && locations.length === 0 && (
        <div className={`px-4 py-2 border-b ${th.border} ${th.jurisdBar} text-[11px] text-zinc-500`}>
          Compliance locations unavailable — check your plan or contact support.
        </div>
      )}
      {complianceMode && locations.length > 0 && (
        <div className={`px-4 py-2 border-b ${th.border} ${th.jurisdBar} flex items-center gap-2 overflow-x-auto`}>
          <MapPin size={12} className="text-cyan-500 shrink-0" />
          <span className={`text-[10px] ${th.jurisdLabel} uppercase tracking-wider font-medium shrink-0`}>Your jurisdictions:</span>
          <div className="flex gap-1.5 flex-wrap">
            {locations.map((loc) => (
              <span
                key={loc.id}
                className="text-[11px] bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 px-2 py-0.5 rounded whitespace-nowrap"
              >
                {loc.city}, {loc.state}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
