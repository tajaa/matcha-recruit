import { useMemo, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { ToggleLeft, Search, Loader2 } from 'lucide-react'
import { Badge, Toggle, LABEL } from '../../components/ui'
import { api } from '../../api/client'
import { FEATURE_GROUPS, FEATURE_LABELS, FEATURE_KEYS } from '../../data/featureCatalog'


type CompanyFeatures = {
  id: string
  company_name: string
  enabled_features: Record<string, boolean>
  is_test: boolean
}

type FeatureFlagStatus = {
  key: string
  is_beta: boolean
  non_test_enabled_count: number
}

type ProvenanceBucket =
  | 'tier_forced' | 'addon' | 'custom_product' | 'paid_gate' | 'tier_preset' | 'audit' | 'unknown'

type ProvenanceEntry = { bucket: ProvenanceBucket; detail: unknown }
type PlanInfo = { kind: 'builtin' | 'custom_product' | 'unknown'; slug: string | null; label: string }
type AddonInfo = { key: string; name: string; feature: string }
type ProvenanceResponse = {
  company_id: string
  plan: PlanInfo
  addons: AddonInfo[]
  features: Record<string, ProvenanceEntry>
}

const EMPTY_PROVENANCE: ProvenanceResponse = {
  company_id: '', plan: { kind: 'unknown', slug: null, label: '—' }, addons: [], features: {},
}

const PLAN_BADGE_VARIANT: Record<PlanInfo['kind'], 'success' | 'neutral' | 'warning'> = {
  builtin: 'success',
  custom_product: 'success',
  unknown: 'warning',
}

// Buckets the plan itself grants — everything else enabled is "outside the
// plan": a real add-on purchase, a custom-product grant, a manual toggle, or
// unexplained history. All four read the same to an admin ("we're paying for
// this on top of the plan"), so the Add-ons summary lists them together
// rather than only the formal LiteAddon subset.
const PLAN_BUCKETS = new Set<ProvenanceBucket>(['tier_forced', 'paid_gate', 'tier_preset'])

// Label + tooltip hint per bucket — see server feature_provenance.py for the
// classification rules these summarize.
const PROVENANCE_META: Record<ProvenanceBucket, { label: string; hint: string }> = {
  tier_forced: { label: 'Bundle', hint: 'Always on for this tier — toggling here has no effect at read time.' },
  addon: { label: 'Add-on', hint: 'Granted by a purchased add-on subscription.' },
  custom_product: { label: 'Product', hint: 'Granted by an admin-composed custom product.' },
  paid_gate: { label: 'Paid gate', hint: "This tier's Stripe checkout gate." },
  tier_preset: { label: 'Signup', hint: 'Granted at signup for this tier — admin-toggleable.' },
  audit: { label: 'Manual', hint: 'Traced to a specific admin/webhook write — see the audit log.' },
  unknown: { label: 'Unknown origin', hint: 'Enabled before the audit log existed, or by an untracked path.' },
}

function enabledCount(features: Record<string, boolean>) {
  return FEATURE_KEYS.filter((k) => features[k]).length
}

export default function Features() {
  const { data: companies, loading, setData: setCompanies } = useAsync(
    () => api.get<CompanyFeatures[]>('/admin/company-features'),
    [],
    [],
  )
  const { data: flagStatuses } = useAsync(
    () => api.get<FeatureFlagStatus[]>('/admin/feature-flags'),
    [],
    [],
  )
  const betaKeys = useMemo(
    () => new Set(flagStatuses.filter((f) => f.is_beta).map((f) => f.key)),
    [flagStatuses]
  )
  const [search, setSearch] = useState('')
  const [toggling, setToggling] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(
    () => companies.filter((c) => c.company_name.toLowerCase().includes(search.toLowerCase())),
    [companies, search]
  )

  // Auto-select the first visible row so the detail pane is never empty when
  // there's something to show, and drop the selection once it scrolls out of
  // the filtered list.
  const selected = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null

  const { data: provenance } = useAsync(
    () => (selected
      ? api.get<ProvenanceResponse>(`/admin/company-features/${selected.id}/provenance`)
      : Promise.resolve(EMPTY_PROVENANCE)),
    [selected?.id],
    EMPTY_PROVENANCE,
  )
  // Everything enabled that the plan itself doesn't grant — a real add-on
  // purchase, a custom product, a manual toggle, or unexplained history.
  const outsidePlanEntries = useMemo(
    () => Object.entries(provenance.features).filter(([, p]) => !PLAN_BUCKETS.has(p.bucket)),
    [provenance],
  )

  async function toggle(companyId: string, feature: string, enabled: boolean) {
    const key = `${companyId}:${feature}`
    setToggling(key)
    setError(null)
    try {
      const res = await api.patch<{ enabled_features: Record<string, boolean> }>(
        `/admin/company-features/${companyId}`,
        { feature, enabled }
      )
      setCompanies((prev) =>
        prev.map((c) => (c.id === companyId ? { ...c, enabled_features: res.enabled_features } : c))
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Toggle failed')
    } finally {
      setToggling(null)
    }
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Company list */}
      <div className="flex w-72 shrink-0 flex-col border-r border-white/[0.06]">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-3">
          <ToggleLeft className="h-4 w-4 shrink-0 text-emerald-400" />
          <h1 className="text-sm font-semibold text-zinc-100">Features</h1>
        </div>
        <div className="border-b border-white/[0.06] p-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tenants…"
              autoFocus
              className="w-full rounded-md border border-white/[0.08] bg-white/[0.03] py-1.5 pl-8 pr-2 text-[13px] text-zinc-200 placeholder-zinc-500 outline-none focus:border-white/[0.16]"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-3"><Loader2 className="h-4 w-4 animate-spin text-zinc-500" /></div>
          ) : filtered.length === 0 ? (
            <p className="p-3 text-xs text-zinc-500">No tenants found.</p>
          ) : (
            filtered.map((c) => {
              const count = enabledCount(c.enabled_features)
              const isSelected = selected?.id === c.id
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={`flex w-full items-center justify-between gap-2 border-l-2 px-3 py-2 text-left transition-colors ${
                    isSelected
                      ? 'border-emerald-400 bg-white/[0.05]'
                      : 'border-transparent hover:bg-white/[0.03]'
                  }`}
                >
                  <span className={`truncate text-[13px] ${isSelected ? 'text-zinc-100 font-medium' : 'text-zinc-300'}`}>
                    {c.company_name}
                  </span>
                  <span className={`shrink-0 text-[11px] font-mono ${count > 0 ? 'text-emerald-400' : 'text-zinc-600'}`}>
                    {count}/{FEATURE_KEYS.length}
                  </span>
                </button>
              )
            })
          )}
        </div>
        <div className="border-t border-white/[0.06] px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-zinc-600">
          {companies.length} tenants
        </div>
      </div>

      {/* Detail pane */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {error && (
          <p className="mx-4 mt-4 rounded border border-red-900/30 bg-red-950/30 px-3 py-2 text-sm text-red-400">
            {error}
          </p>
        )}
        {!selected ? (
          <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
            Select a tenant to manage its features.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-zinc-100">{selected.company_name}</h2>
                {selected.is_test && <Badge variant="neutral">Test account</Badge>}
              </div>
              <Badge variant={enabledCount(selected.enabled_features) > 0 ? 'success' : 'neutral'}>
                {enabledCount(selected.enabled_features)}/{FEATURE_KEYS.length} enabled
              </Badge>
            </div>
            <div className="space-y-2.5 border-b border-white/[0.06] px-4 py-3">
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-zinc-500">Plan</span>
                <Badge variant={PLAN_BADGE_VARIANT[provenance.plan.kind]}>{provenance.plan.label}</Badge>
                {provenance.plan.kind === 'unknown' && (
                  <span className="text-[11px] text-zinc-600">
                    (signup_source doesn't match a known tier or product)
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-zinc-500">Add-ons</span>
                {outsidePlanEntries.length === 0 ? (
                  <span className="text-[11px] text-zinc-600">Nothing enabled outside the plan</span>
                ) : (
                  outsidePlanEntries.map(([key, p]) => (
                    <span
                      key={key}
                      title={PROVENANCE_META[p.bucket].hint}
                      className="flex items-center gap-1 rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-0.5 text-[11px] text-zinc-300"
                    >
                      {FEATURE_LABELS[key] ?? key}
                      <span className="text-zinc-600">· {PROVENANCE_META[p.bucket].label}</span>
                    </span>
                  ))
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-zinc-500">Beta</span>
                {betaKeys.size === 0 ? (
                  <span className="text-[11px] text-zinc-600">No features currently in beta</span>
                ) : (
                  Array.from(betaKeys).map((key) => {
                    const on = !!selected.enabled_features[key]
                    return (
                      <span
                        key={key}
                        className={`rounded border px-1.5 py-0.5 text-[11px] ${
                          on
                            ? 'border-amber-800/40 bg-amber-950/30 text-amber-300'
                            : 'border-white/[0.08] bg-white/[0.03] text-zinc-500'
                        }`}
                      >
                        {FEATURE_LABELS[key] ?? key}{on ? ' — enabled' : ''}
                      </span>
                    )
                  })
                )}
              </div>
            </div>
            {Object.values(provenance.features).some((p) => p.bucket === 'unknown') && (
              <p className="border-b border-white/[0.06] bg-white/[0.02] px-4 py-1.5 text-[11px] text-zinc-500">
                Some enabled features show "Unknown origin" — they predate the write audit log
                (feataudit01) or came from a path it doesn't yet cover. That's expected for
                older grants, not a bug.
              </p>
            )}
            <div className="flex-1 space-y-5 overflow-y-auto p-4">
              {FEATURE_GROUPS.map((group) => (
                <div key={group.label}>
                  <div className={`mb-2 ${LABEL}`}>{group.label}</div>
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-5 gap-y-3">
                    {Object.keys(group.features).map((key) => {
                      const on = !!selected.enabled_features[key]
                      const busy = toggling === `${selected.id}:${key}`
                      const isBeta = betaKeys.has(key)
                      // Beta features can only be switched ON for test companies —
                      // turning one OFF (remediation) always stays live.
                      const lockedOn = isBeta && !on && !selected.is_test
                      const prov = on ? provenance.features[key] : undefined
                      const provMeta = prov ? PROVENANCE_META[prov.bucket] : undefined
                      // A tier-forced flag is re-forced by merge_company_features on
                      // every read regardless of what's stored — toggling it here is
                      // a no-op at read time, so don't offer a toggle that lies.
                      const tierForced = prov?.bucket === 'tier_forced'
                      const title = lockedOn
                        ? `${FEATURE_LABELS[key]} — beta, test accounts only`
                        : provMeta
                          ? `${FEATURE_LABELS[key]} — ${provMeta.hint}`
                          : FEATURE_LABELS[key]
                      return (
                        <div key={key} className="flex items-center gap-3">
                          <span
                            className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-xs text-zinc-400"
                            title={title}
                          >
                            <span className="truncate">{FEATURE_LABELS[key]}</span>
                            {isBeta && (
                              <Badge variant="warning" className="shrink-0">Beta</Badge>
                            )}
                            {provMeta && (
                              <Badge variant="neutral" className="shrink-0">{provMeta.label}</Badge>
                            )}
                          </span>
                          <Toggle
                            checked={on}
                            disabled={busy || lockedOn || tierForced}
                            onChange={(v) => toggle(selected.id, key, v)}
                            size="sm"
                          />
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
