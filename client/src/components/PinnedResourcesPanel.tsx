import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Pin, X } from 'lucide-react'

import { usePinnedResources } from '../hooks/usePinnedResources'
import { ensureStateGuideLabels, resolveResourcePin } from '../data/resourceCatalog'

/**
 * Dashboard widget rendered above the resource category grid. Shows the
 * user's pinned resources as compact chips. Empty state nudges users to
 * pin from any list. Hidden until first load resolves so the panel
 * doesn't flash empty before pins arrive.
 */
export default function PinnedResourcesPanel() {
  const { pins, togglePin, loading } = usePinnedResources()

  useEffect(() => {
    // Trigger the state-guide label fetch in case any pin is a state guide.
    // Cheap no-op when no state-guide pins exist.
    if (pins.some(p => p.kind === 'state_guide')) {
      void ensureStateGuideLabels()
    }
  }, [pins])

  if (loading) return null

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Pin className="w-3.5 h-3.5 text-vsc-text/50" />
        <h2 className="text-xs font-medium uppercase tracking-wider text-vsc-text/50">
          Pinned
        </h2>
      </div>
      {pins.length === 0 ? (
        <div className="rounded-lg border border-dashed border-vsc-border bg-vsc-panel/40 px-4 py-5 text-xs text-vsc-text/50">
          Pin resources from any page to see them here for quick access.
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {pins.map((pin) => {
            const spec = resolveResourcePin(pin.kind, pin.id)
            return (
              <div
                key={`${pin.kind}:${pin.id}`}
                className="group flex items-center gap-2 rounded-lg border border-vsc-border bg-vsc-panel pl-3 pr-1 py-1.5 hover:border-vsc-text/30 transition-colors"
              >
                <Link to={spec.route} className="flex items-center gap-2 min-w-0">
                  <spec.Icon className="w-3.5 h-3.5 text-vsc-text/60 shrink-0" />
                  <span className="text-xs text-vsc-text truncate max-w-[180px]">
                    {spec.label}
                  </span>
                  {spec.description && (
                    <span className="text-[10px] text-vsc-text/40 truncate max-w-[120px]">
                      {spec.description}
                    </span>
                  )}
                </Link>
                <button
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    void togglePin(pin.kind, pin.id)
                  }}
                  className="p-1 rounded text-vsc-text/30 hover:text-vsc-text hover:bg-black/5 transition-colors"
                  aria-label="Unpin"
                  title="Unpin"
                >
                  <X size={12} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
