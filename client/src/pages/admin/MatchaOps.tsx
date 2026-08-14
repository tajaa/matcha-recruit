import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Boxes, CalendarDays, ClipboardList, Loader2, MessageSquare, Search, Users } from 'lucide-react'
import { getOpsCompany, getOpsOverview, listOpsCompanies, updateOpsCompanyFeatures, type OpsCompany, type OpsCompanyDetail, type OpsOverview } from '../../api/admin/matchaOps'
import { Badge, Button, Input, Toggle, useToast } from '../../components/ui'
import { FEATURE_REQUIRES } from '../../data/featureCatalog'

const OPS_FLAGS: { key: string; label: string; description: string }[] = [
  { key: 'matcha_ops', label: 'Matcha Ops', description: 'Company Operations surface and channels' },
  { key: 'ems', label: 'Events', description: 'Event intake and review' },
  { key: 'inventory', label: 'Inventory', description: 'Inventory and order tracking' },
  { key: 'inventory_voice', label: 'Inventory Voice', description: 'Voice audit parsing' },
  { key: 'employee_schedule', label: 'Schedule', description: 'Shifts and employee requests' },
  { key: 'schedule_intelligence', label: 'Schedule Intelligence', description: 'Schedule analytics' },
  { key: 'matcha_ops_calls_all_members', label: 'Member Call Starts', description: 'Allow any member to start calls' },
]
const OPS_FLAG_KEYS = new Set(OPS_FLAGS.map((flag) => flag.key))

function Stat({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Users }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4"><div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500"><Icon className="h-4 w-4 text-emerald-400" />{label}</div><div className="mt-2 text-2xl font-semibold text-zinc-100">{value}</div></div>
}

export default function MatchaOps() {
  const { toast } = useToast()
  const [overview, setOverview] = useState<OpsOverview | null>(null)
  const [companies, setCompanies] = useState<OpsCompany[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<OpsCompanyDetail | null>(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [summary, rows] = await Promise.all([getOpsOverview(), listOpsCompanies()])
      setOverview(summary)
      setCompanies(rows.companies)
      setSelectedId((current) => current ?? rows.companies[0]?.company_id ?? null)
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not load Matcha Ops', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    getOpsCompany(selectedId).then(setDetail).catch(() => setDetail(null))
  }, [selectedId])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return companies.filter((company) => !query || company.company_name.toLowerCase().includes(query))
  }, [companies, search])

  async function toggle(key: string, enabled: boolean) {
    if (!detail) return
    const next = { ...detail.effective_features }
    const visit = (feature: string, value: boolean, seen = new Set<string>()) => {
      if (seen.has(feature)) return
      seen.add(feature)
      if (!value) {
        for (const [dependent, requirements] of Object.entries(FEATURE_REQUIRES)) {
          if (requirements.includes(feature)) visit(dependent, false, seen)
        }
      } else {
        for (const requirement of FEATURE_REQUIRES[feature] ?? []) visit(requirement, true, seen)
      }
      next[feature] = value
    }
    visit(key, enabled)
    const features = Object.fromEntries(
      Object.entries(next).filter(([feature, value]) => OPS_FLAG_KEYS.has(feature) && detail.effective_features[feature] !== value),
    )
    setSaving(true)
    try {
      const next = await updateOpsCompanyFeatures(detail.company_id, features)
      setDetail(next)
      setCompanies((rows) => rows.map((row) => row.company_id === next.company_id ? next : row))
      const summary = await getOpsOverview()
      setOverview(summary)
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not update Ops features', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>

  return <div className="flex h-[calc(100vh-7rem)] min-h-[520px] overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
    <div className="flex w-72 shrink-0 flex-col border-r border-white/[0.06]">
      <div className="border-b border-white/[0.06] p-4"><h1 className="text-lg font-semibold text-zinc-100">Matcha Ops</h1><p className="mt-1 text-xs text-zinc-500">Entitlements and operational health.</p></div>
      <div className="border-b border-white/[0.06] p-3"><div className="relative"><Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" size={14} /><Input label="" placeholder="Search companies..." value={search} onChange={(event) => setSearch(event.target.value)} className="pl-8" /></div></div>
      <div className="flex-1 overflow-y-auto">
        {filtered.map((company) => <button key={company.company_id} type="button" onClick={() => setSelectedId(company.company_id)} className={`w-full border-l-2 px-3 py-3 text-left ${selectedId === company.company_id ? 'border-emerald-400 bg-white/[0.05]' : 'border-transparent hover:bg-white/[0.03]'}`}><div className="flex items-center justify-between gap-2"><span className="truncate text-sm text-zinc-200">{company.company_name}</span>{company.needs_attention && <AlertTriangle size={14} className="shrink-0 text-amber-400" />}</div><div className="mt-1 text-[11px] text-zinc-500">{company.matcha_ops_enabled ? `${company.operations_channel_count} Ops channels` : 'Ops disabled'}</div></button>)}
        {filtered.length === 0 && <p className="p-4 text-xs text-zinc-500">No companies found.</p>}
      </div>
      <div className="border-t border-white/[0.06] p-3 text-[10px] uppercase tracking-wider text-zinc-600">{companies.length} companies</div>
    </div>
    <div className="flex-1 overflow-y-auto p-5">
      {overview && <div className="grid grid-cols-2 gap-3 md:grid-cols-4"><Stat label="Ops companies" value={overview.companies_enabled} icon={Users} /><Stat label="Channels" value={overview.operations_channels} icon={MessageSquare} /><Stat label="Open events" value={overview.open_events} icon={ClipboardList} /><Stat label="Upcoming shifts" value={overview.upcoming_shifts} icon={CalendarDays} /></div>}
      {!detail ? <div className="flex min-h-64 items-center justify-center text-sm text-zinc-500">Select a company.</div> : <div className="mt-6 space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold text-zinc-100">{detail.company_name}</h2><p className="mt-1 text-xs text-zinc-500">{detail.signup_source ?? 'legacy company'} · {detail.status}</p></div><Badge variant={detail.needs_attention ? 'warning' : detail.matcha_ops_enabled ? 'success' : 'neutral'}>{detail.needs_attention ? 'Needs attention' : detail.matcha_ops_enabled ? 'Ops enabled' : 'Ops disabled'}</Badge></div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5"><Stat label="Events" value={detail.open_events} icon={ClipboardList} /><Stat label="Low stock" value={detail.low_stock_items} icon={Boxes} /><Stat label="Open orders" value={detail.open_orders} icon={Boxes} /><Stat label="Requests" value={detail.pending_schedule_requests} icon={CalendarDays} /><Stat label="Channels" value={detail.channel_count} icon={MessageSquare} /></div>
        {Object.keys(detail.dependency_violations).length > 0 && <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">This tenant has an invalid dependency state. Resolve the parent/child flags below.</div>}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30"><div className="border-b border-zinc-800 px-4 py-3"><h3 className="text-sm font-medium text-zinc-200">Entitlements</h3><p className="mt-1 text-xs text-zinc-500">Changes are validated atomically and audited.</p></div><div className="divide-y divide-zinc-800">{OPS_FLAGS.map((flag) => <div key={flag.key} className="flex items-center justify-between gap-4 px-4 py-3"><div><p className="text-sm text-zinc-200">{flag.label}</p><p className="text-xs text-zinc-500">{flag.description}</p></div><Toggle checked={!!detail.effective_features[flag.key]} disabled={saving} onChange={(value) => void toggle(flag.key, value)} /></div>)}</div></div>
        <Button variant="ghost" onClick={() => void load()}>Refresh</Button>
      </div>}
    </div>
  </div>
}
