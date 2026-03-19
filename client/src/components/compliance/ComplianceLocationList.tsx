import { useState } from 'react'
import { Button } from '../ui'
import type { BusinessLocation } from '../../types/compliance'

type Props = {
  locations: BusinessLocation[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  onEdit: (location: BusinessLocation) => void
  onDelete: (id: string) => void
  onAdd: () => void
  loading: boolean
}

export function ComplianceLocationList({ locations, selectedId, onSelect, onEdit, onDelete, onAdd, loading }: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  if (loading) {
    return (
      <div>
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Locations</h2>
        <p className="text-sm text-zinc-500">Loading...</p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Locations</h2>
      <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
        {locations.length === 0 && (
          <p className="px-4 py-3 text-sm text-zinc-600">No locations added yet.</p>
        )}
        {locations.map((loc) => (
          <div key={loc.id}>
            <button type="button"
              onClick={() => onSelect(loc.id === selectedId ? null : loc.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors border-l-2 ${
                loc.id === selectedId
                  ? 'bg-zinc-800/60 border-zinc-300'
                  : 'hover:bg-zinc-800/30 border-transparent'
              }`}>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-zinc-200 truncate">
                  {loc.city}, {loc.state}
                  {loc.name && <span className="text-zinc-500 ml-1.5">({loc.name})</span>}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-zinc-500">{loc.requirements_count} requirements</span>
                  {loc.employee_count > 0 && (
                    <span className="text-[11px] text-zinc-600">{loc.employee_count} employees</span>
                  )}
                  {loc.source === 'employee_derived' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/30 text-purple-400 border border-purple-800/40">Employee</span>
                  )}
                  {loc.has_local_ordinance && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-800/40">Local</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                {loc.data_status === 'needs_research' && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40">Needs Sync</span>
                )}
                {loc.unread_alerts_count > 0 && (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                )}
              </div>
            </button>
            {loc.id === selectedId && (
              <div className="flex items-center gap-2 px-3 pb-2">
                <button type="button" onClick={() => onEdit(loc)}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Edit</button>
                {confirmDeleteId === loc.id ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-zinc-500">Delete?</span>
                    <button type="button" onClick={() => { onDelete(loc.id); setConfirmDeleteId(null) }}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors">Yes</button>
                    <button type="button" onClick={() => setConfirmDeleteId(null)}
                      className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">No</button>
                  </div>
                ) : (
                  <button type="button" onClick={() => setConfirmDeleteId(loc.id)}
                    className="text-xs text-zinc-600 hover:text-red-400 transition-colors">Delete</button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2">
        <Button variant="ghost" size="sm" onClick={onAdd}>+ Add Location</Button>
      </div>
    </div>
  )
}
