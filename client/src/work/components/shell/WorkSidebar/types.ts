/** Sidebar "TABS" strip — the browser-tab-like strip of recently opened items
 *  desktop Werk keeps in `WorkTabsSidebarSection`. Persisted per work surface so
 *  /work and /werk don't bleed into each other. */
export type OpenTab = { type: 'channel' | 'project' | 'thread'; id: string; label: string }
export const MAX_OPEN_TABS = 6

export interface Props {
  open: boolean
  onToggle: () => void
}

export type RenameItem = { type: 'channel' | 'project' | 'thread'; id: string; name: string }
