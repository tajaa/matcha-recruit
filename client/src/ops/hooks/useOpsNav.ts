import { useEffect, useState } from 'react'
import { CalendarDays, ClipboardList, Hash, Home, Package, Recycle, ShieldCheck } from 'lucide-react'
import { listChannels } from '../../work/api/channels'
import type { ChannelSummary } from '../../work/api/channels'
import { useMe } from '../../hooks/useMe'
import type { NavGroup, NavItem } from '../../components/sidebars/SidebarShell'

/**
 * The "Ops" side of the sidebar's Matcha | Ops switch — every /ops page, each
 * row gated by its own company flag (SidebarShell enforces `feature`), plus the
 * company's operations channels. The Matcha side is the tenant's regular nav.
 */
export function buildOpsNav(channels: ChannelSummary[]): (NavItem | NavGroup)[] {
  return [
    { to: '/ops', icon: Home, label: 'Home' },
    { to: '/ops/events', icon: ClipboardList, label: 'Events', feature: 'ems' },
    { to: '/ops/inventory', icon: Package, label: 'Inventory', feature: 'inventory' },
    { to: '/ops/inventory/waste', icon: Recycle, label: 'Waste & par', feature: 'inventory_waste' },
    { to: '/ops/schedule', icon: CalendarDays, label: 'Schedule', feature: 'employee_schedule' },
    { to: '/ops/access', icon: ShieldCheck, label: 'Access' },
    {
      label: 'Channels',
      key: 'ops-channels',
      defaultOpen: true,
      items: [
        { to: '/ops/channels', icon: Hash, label: 'All channels' },
        ...channels.map((c) => ({
          to: `/ops/channels/${c.id}`,
          icon: Hash,
          label: c.name,
          badge: c.unread_count > 0 ? c.unread_count : undefined,
        })),
      ],
    },
  ]
}

/** Ops nav for a company with `matcha_ops`; null (no switch) otherwise. */
export function useOpsNav(enabled: boolean): (NavItem | NavGroup)[] | null {
  const { hasFeature } = useMe()
  const on = enabled && hasFeature('matcha_ops')
  const [channels, setChannels] = useState<ChannelSummary[]>([])

  useEffect(() => {
    if (!on) return
    let live = true
    listChannels({ scope: 'operations' })
      .then((list) => { if (live) setChannels(list) })
      .catch(() => {})
    return () => { live = false }
  }, [on])

  return on ? buildOpsNav(channels) : null
}
