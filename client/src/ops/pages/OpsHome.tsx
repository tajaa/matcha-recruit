import { ArrowRight, CalendarDays, ClipboardList, Hash, Package } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useWorkBase } from '../../work/routes/WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'

export default function OpsHome() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { hasFeature } = useMe()
  const cards = [
    { feature: 'ems', path: '/events', label: 'Events', description: 'Capture and review operational events.', icon: ClipboardList },
    { feature: 'inventory', path: '/inventory', label: 'Inventory', description: 'Track stock, movements, and orders.', icon: Package },
    { feature: 'employee_schedule', path: '/schedule', label: 'Schedule', description: 'Plan shifts and manage requests.', icon: CalendarDays },
  ]
  return <div className="mx-auto max-w-4xl p-6"><div className="flex items-center gap-3"><Hash className="text-w-accent" size={20} /><div><h1 className="text-xl font-semibold text-w-text">Matcha Ops</h1><p className="mt-1 text-sm text-w-dim">The operational layer for your company.</p></div></div><div className="mt-8 grid gap-4 md:grid-cols-3">{cards.filter((card) => hasFeature(card.feature)).map((card) => <button key={card.path} onClick={() => navigate(`${base}${card.path}`)} className="group rounded-xl border border-w-line bg-w-surface p-4 text-left transition-colors hover:border-w-accent/50"><card.icon className="text-w-accent" size={20} /><h2 className="mt-5 text-sm font-medium text-w-text">{card.label}</h2><p className="mt-1 text-xs leading-5 text-w-dim">{card.description}</p><ArrowRight className="mt-5 text-w-faint transition-transform group-hover:translate-x-1 group-hover:text-w-accent" size={15} /></button>)}</div></div>
}
