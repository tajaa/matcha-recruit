import { useState } from 'react'
import { ShowMoreRow } from './SidebarSection'

/** The rows a capped list shows: the first `limit`, plus any `keep` says must
 *  stay visible (unread, open), unless expanded or filtering. */
export function useCappedList<T>(items: T[], limit: number, { filtering = false, keep }: {
  filtering?: boolean
  keep?: (item: T) => boolean
} = {}) {
  const [expanded, setExpanded] = useState(false)
  const all = expanded || filtering
  const visible = all ? items : items.filter((item, i) => i < limit || !!keep?.(item))
  return {
    visible,
    toggle: !filtering && items.length > limit ? (
      <ShowMoreRow hidden={items.length - visible.length} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
    ) : null,
  }
}
