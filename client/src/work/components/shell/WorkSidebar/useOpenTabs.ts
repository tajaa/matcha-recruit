import { useEffect, useState } from 'react'
import type { ChannelSummary } from '../../../api/channels'
import type { MWThread, MWProject } from '../../../types'
import type { OpenTab } from './types'
import { MAX_OPEN_TABS } from './types'

/** Tracks the currently-open channel/project/thread into the TABS strip —
 *  upsert-to-front, capped, persisted per work surface. */
export function useOpenTabs(
  base: string,
  pathname: string,
  channels: ChannelSummary[],
  projects: MWProject[],
  threads: MWThread[],
) {
  const tabsKey = `mw-open-tabs:${base}`
  const [openTabs, setOpenTabs] = useState<OpenTab[]>(() => {
    // Validate shape, not just JSON syntax: a valid-but-wrong value (`{}`, a
    // string, entries missing `type`) would otherwise survive parse and then
    // blow up in `prev.filter` / `tabIcon[t.type]` on the next navigation.
    try {
      const raw: unknown = JSON.parse(localStorage.getItem(tabsKey) || '[]')
      if (!Array.isArray(raw)) return []
      return raw.filter(
        (t): t is OpenTab =>
          !!t &&
          typeof t === 'object' &&
          typeof (t as OpenTab).id === 'string' &&
          typeof (t as OpenTab).label === 'string' &&
          ['channel', 'project', 'thread'].includes((t as OpenTab).type),
      )
    } catch {
      return []
    }
  })

  // Track the currently-open channel/project/thread into the TABS strip —
  // upsert-to-front, capped, persisted per work surface. Only fires once the
  // matching list has loaded so the label is real, not a placeholder.
  useEffect(() => {
    const path = pathname
    let entry: OpenTab | null = null
    const channelMatch = path.match(new RegExp(`^${base}/channels/([^/]+)$`))
    const projectMatch = path.match(new RegExp(`^${base}/projects/([^/]+)$`))
    const threadMatch = path.match(new RegExp(`^${base}/([^/]+)$`))
    if (channelMatch) {
      const ch = channels.find((c) => c.id === channelMatch[1])
      if (ch) entry = { type: 'channel', id: ch.id, label: ch.name }
    } else if (projectMatch) {
      const p = projects.find((x) => x.id === projectMatch[1])
      if (p) entry = { type: 'project', id: p.id, label: p.title }
    } else if (threadMatch && threadMatch[1] !== 'email' && threadMatch[1] !== 'inbox' && threadMatch[1] !== 'connections' && threadMatch[1] !== 'billing' && threadMatch[1] !== 'channels') {
      const t = threads.find((x) => x.id === threadMatch[1])
      if (t) entry = { type: 'thread', id: t.id, label: t.title }
    }
    setOpenTabs((prev) => {
      // Re-label stored tabs from the freshly loaded lists, so renaming an item
      // that isn't the currently-open one doesn't strand a stale label forever.
      const relabelled = prev.map((t) => {
        const src =
          t.type === 'channel' ? channels.find((c) => c.id === t.id)?.name
          : t.type === 'project' ? projects.find((p) => p.id === t.id)?.title
          : threads.find((x) => x.id === t.id)?.title
        return src && src !== t.label ? { ...t, label: src } : t
      })
      const next = entry
        ? [entry, ...relabelled.filter((t) => !(t.type === entry!.type && t.id === entry!.id))].slice(0, MAX_OPEN_TABS)
        : relabelled
      // Bail out when nothing actually changed — this effect re-runs on every
      // list refetch (channel create/join, home navigation), and writing an
      // identical array would re-render the sidebar and hit localStorage each time.
      const same =
        next.length === prev.length &&
        next.every((t, i) => t.type === prev[i].type && t.id === prev[i].id && t.label === prev[i].label)
      if (same) return prev
      try {
        localStorage.setItem(tabsKey, JSON.stringify(next))
      } catch {}
      return next
    })
  }, [pathname, channels, projects, threads])

  function closeTab(e: React.MouseEvent, tab: OpenTab) {
    e.stopPropagation()
    setOpenTabs((prev) => {
      const next = prev.filter((t) => !(t.type === tab.type && t.id === tab.id))
      try {
        localStorage.setItem(tabsKey, JSON.stringify(next))
      } catch {}
      return next
    })
  }

  function openTabPath(tab: OpenTab): string {
    if (tab.type === 'channel') return `${base}/channels/${tab.id}`
    if (tab.type === 'project') return `${base}/projects/${tab.id}`
    return `${base}/${tab.id}`
  }

  return { openTabs, closeTab, openTabPath }
}
