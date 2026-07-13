// Shared bits for the Cappe incidents surface (list + detail pages).
// Cappe-styled — deliberately independent of matcha's components/ir/*.

import { ShieldAlert } from 'lucide-react'
import type {
  CappeIrActionStatus,
  CappeIrIncidentType,
  CappeIrLocation,
  CappeIrSeverity,
  CappeIrStatus,
} from '../../../api/cappeIr'

export const inputCls =
  'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-500'

export const statusStyle: Record<CappeIrStatus, string> = {
  reported: 'bg-sky-500/15 text-sky-400',
  investigating: 'bg-amber-500/15 text-amber-400',
  action_required: 'bg-orange-500/15 text-orange-400',
  resolved: 'bg-emerald-500/15 text-emerald-400',
  closed: 'bg-zinc-800 text-zinc-500',
}

export const severityStyle: Record<CappeIrSeverity, string> = {
  critical: 'bg-red-500/15 text-red-400',
  high: 'bg-orange-500/15 text-orange-400',
  medium: 'bg-amber-500/15 text-amber-400',
  low: 'bg-zinc-800 text-zinc-400',
}

export const typeStyle: Record<CappeIrIncidentType, string> = {
  safety: 'bg-red-500/15 text-red-400',
  behavioral: 'bg-violet-500/15 text-violet-400',
  property: 'bg-sky-500/15 text-sky-400',
  near_miss: 'bg-amber-500/15 text-amber-400',
  other: 'bg-zinc-800 text-zinc-400',
}

export const actionStatusStyle: Record<CappeIrActionStatus, string> = {
  open: 'bg-sky-500/15 text-sky-400',
  in_progress: 'bg-amber-500/15 text-amber-400',
  completed: 'bg-emerald-500/15 text-emerald-400',
  verified: 'bg-lime-400/15 text-lime-300',
  cancelled: 'bg-zinc-800 text-zinc-500',
}

/** Human label for a snake_case enum value ("near_miss" → "Near miss"). */
export function labelFor(value: string): string {
  const s = value.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function formatLocation(l: CappeIrLocation): string {
  return l.name ? `${l.name} — ${l.city}, ${l.state}` : `${l.city}, ${l.state} ${l.zipcode}`
}

export function formatBytes(size: number | null): string {
  if (size == null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** Friendly panel for accounts without the bridged `incidents` feature. */
export function FeatureOffPanel() {
  return (
    <div className="rounded-2xl border border-dashed border-zinc-700 py-14 text-center">
      <ShieldAlert className="mx-auto mb-3 h-8 w-8 text-zinc-500" />
      <p className="text-sm font-medium text-zinc-200">Incident reporting isn't enabled for your account</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-zinc-500">
        Track safety and workplace incidents, corrective actions, and supporting documents.
        Contact support to add it to your plan.
      </p>
    </div>
  )
}
