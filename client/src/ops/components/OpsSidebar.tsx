import { useEffect, useState } from 'react'
import { CalendarDays, Hash, Home, Package, PanelLeftClose, ClipboardList, ShieldCheck } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { listChannels } from '../../work/api/channels'
import type { ChannelSummary } from '../../work/api/channels'
import { useWorkBase } from '../../work/routes/WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'
import type { Props } from '../../work/components/shell/WorkSidebar/types'

export default function OpsSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = useWorkBase()
  const { hasFeature } = useMe()
  const [channels, setChannels] = useState<ChannelSummary[]>([])

  useEffect(() => {
    listChannels({ scope: 'operations' }).then(setChannels).catch(() => {})
  }, [])

  const active = (path: string) => location.pathname === path || location.pathname.startsWith(`${path}/`)
  const go = (path: string) => navigate(`${base}${path}`)

  if (!open) return <aside className="w-12 shrink-0 border-r border-w-line bg-w-surface py-2"><button onClick={onToggle} className="mx-auto block p-2 text-w-dim hover:text-white" title="Open sidebar"><PanelLeftClose size={16} className="rotate-180" /></button><button onClick={() => go('')} className="mx-auto mt-2 block p-2 text-w-dim hover:text-white" title="Home"><Home size={16} /></button><button onClick={() => go('/channels')} className="mx-auto block p-2 text-w-dim hover:text-white" title="Channels"><Hash size={16} /></button></aside>

  return <aside className="flex w-56 shrink-0 flex-col overflow-hidden border-r border-w-line bg-w-surface">
    <div className="flex items-center gap-2 px-3 py-3"><span className="flex-1 text-[13px] font-semibold text-w-text">Matcha Ops</span><button onClick={onToggle} className="p-1 text-w-dim hover:text-white" title="Collapse sidebar"><PanelLeftClose size={16} /></button></div>
    <nav className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
      <button onClick={() => go('')} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(base) && location.pathname === base ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><Home size={14} /> Home</button>
      <div className="mt-3 px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-w-dim">Operations</div>
      {hasFeature('ems') && <button onClick={() => go('/events')} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(`${base}/events`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><ClipboardList size={14} /> Events</button>}
      {hasFeature('inventory') && <button onClick={() => go('/inventory')} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(`${base}/inventory`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><Package size={14} /> Inventory</button>}
       {hasFeature('employee_schedule') && <button onClick={() => go('/schedule')} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(`${base}/schedule`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><CalendarDays size={14} /> Schedule</button>}
       <button onClick={() => go('/access')} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(`${base}/access`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><ShieldCheck size={14} /> Access</button>
      <div className="mt-3 flex items-center justify-between px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-w-dim"><span>Channels</span><button onClick={() => go('/channels')} className="text-w-dim hover:text-w-accent"><Hash size={12} /></button></div>
      {channels.map((channel) => <button key={channel.id} onClick={() => go(`/channels/${channel.id}`)} className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] ${active(`${base}/channels/${channel.id}`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}><Hash size={14} /> <span className="truncate">{channel.name}</span>{channel.unread_count > 0 && <span className="ml-auto text-[10px] text-w-accent">{channel.unread_count}</span>}</button>)}
      {channels.length === 0 && <p className="px-2.5 py-1 text-[11px] text-w-faint">No channels</p>}
    </nav>
  </aside>
}
