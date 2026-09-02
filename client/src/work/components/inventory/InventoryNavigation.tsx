import { BarChart3, Boxes, ClipboardList, ShoppingCart } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMe } from '../../../hooks/useMe'
import { useWorkBase } from '../../routes/WorkSurfaceContext'

export default function InventoryNavigation() {
  const base = useWorkBase()
  const navigate = useNavigate()
  const location = useLocation()
  const { hasFeature } = useMe()
  const tabs = [
    { label: 'Inventory', icon: Boxes, href: `${base}/inventory`, visible: true, active: location.pathname === `${base}/inventory` || /^.+\/inventory\/[^/]+$/.test(location.pathname) },
    { label: 'Waste & loss', icon: ClipboardList, href: `${base}/inventory/waste`, visible: hasFeature('inventory_waste'), active: location.pathname === `${base}/inventory/waste` },
    { label: 'Insights & PARs', icon: BarChart3, href: `${base}/inventory/forecast`, visible: hasFeature('inventory_forecasting'), active: location.pathname === `${base}/inventory/forecast` },
    { label: 'Buying guidance', icon: ShoppingCart, href: `${base}/inventory/buying`, visible: hasFeature('inventory_forecasting'), active: location.pathname === `${base}/inventory/buying` },
  ]

  return <nav aria-label="Inventory sections" className="flex gap-1 overflow-x-auto border-b border-w-line pb-3">
    {tabs.filter((tab) => tab.visible).map((tab) => {
      const Icon = tab.icon
      return <button key={tab.href} type="button" onClick={() => navigate(tab.href)} aria-current={tab.active ? 'page' : undefined} className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${tab.active ? 'bg-w-accent text-white' : 'text-w-dim hover:bg-w-surface hover:text-w-text'}`}><Icon size={14} />{tab.label}</button>
    })}
  </nav>
}
