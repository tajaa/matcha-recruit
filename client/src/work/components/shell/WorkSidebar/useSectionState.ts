import { useEffect, useState } from 'react'

export type SidebarSectionKey = 'chats' | 'channels' | 'projects'

type SectionState = Record<SidebarSectionKey, boolean>

const DEFAULTS: SectionState = { chats: true, channels: true, projects: true }

/** Persisted open/closed state for the sidebar's collapsible sections, keyed
 * per work surface (/work vs /werk) so they don't bleed into each other.
 * Defaults to all-open — the old per-section `useState(false)` meant every
 * reload showed three collapsed headers and nothing else. */
export function useSectionState(base: string) {
  const storageKey = `mw-sidebar-sections:${base}`
  const [state, setState] = useState<SectionState>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
    } catch {
      return DEFAULTS
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(state))
    } catch {}
  }, [storageKey, state])

  function toggle(key: SidebarSectionKey) {
    setState((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  function open(key: SidebarSectionKey) {
    setState((prev) => ({ ...prev, [key]: true }))
  }

  return { ...state, toggle, open }
}
