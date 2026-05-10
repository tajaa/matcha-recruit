import { Pin, PinOff } from 'lucide-react'

import type { ResourceKind } from '../api/resourcePins'
import { usePinnedResources } from '../hooks/usePinnedResources'

/**
 * Reusable pin/unpin toggle. Hosted inside `<Link>` rows on every
 * resource list, so the click handler stops propagation to avoid
 * navigating before the toggle fires.
 */
export function PinButton({
  kind,
  id,
  className,
  size = 14,
}: {
  kind: ResourceKind
  id: string
  className?: string
  size?: number
}) {
  const { isPinned, togglePin } = usePinnedResources()
  const pinned = isPinned(kind, id)
  return (
    <button
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        void togglePin(kind, id)
      }}
      title={pinned ? 'Unpin from dashboard' : 'Pin to dashboard'}
      aria-label={pinned ? 'Unpin from dashboard' : 'Pin to dashboard'}
      className={
        className ??
        'p-1.5 rounded hover:bg-black/5 transition-colors text-stone-500 hover:text-stone-900'
      }
    >
      {pinned ? <PinOff size={size} /> : <Pin size={size} />}
    </button>
  )
}
