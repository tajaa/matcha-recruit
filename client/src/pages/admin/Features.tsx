import { useEffect, useMemo, useRef, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { ToggleLeft, Search, Loader2, Settings2 } from 'lucide-react'
import { Badge, Button, Input, Modal, Select, Toggle, useToast, LABEL } from '../../components/ui'
import { api } from '../../api/client'
import { FEATURE_GROUPS, FEATURE_LABELS, FEATURE_KEYS, FEATURE_REQUIRES } from '../../data/featureCatalog'


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
  | 'tier_forced' | 'addon' | 'custom_product' | 'paid_gate' | 'tier_preset' | 'audit' | 'admin_grant'

type AuditDetail = { source: string; actor_user_id: string | null; created_at: string }
type ProvenanceEntry = { bucket: ProvenanceBucket; detail: AuditDetail | string | null }
type PlanInfo = { kind: 'builtin' | 'custom_product' | 'unknown'; slug: string | null; label: string }
type AddonInfo = { key: string; name: string; feature: string }
type GrantEntry = { grant_type: string; note: string | null; updated_at: string }
type ProvenanceResponse = {
  company_id: string
  plan: PlanInfo
  addons: AddonInfo[]
  features: Record<string, ProvenanceEntry>
  grants: Record<string, GrantEntry>
  grant_types: string[]
}

type BuiltinTierComposition = {
  slug: string
  forced_on: string[]
  forced_off: string[]
}

const EMPTY_PROVENANCE: ProvenanceResponse = {
  company_id: '', plan: { kind: 'unknown', slug: null, label: '—' }, addons: [], features: {},
  grants: {}, grant_types: [],
}

const GRANT_TYPE_LABELS: Record<string, string> = {
  comped: 'Comped',
  invoiced: 'Invoiced',
  trial: 'Trial',
  internal: 'Internal',
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
// classification rules these summarize. `audit` is a placeholder — its real
// label is derived per-row from detail.source (see auditLabel below), since
// an admin_toggle audit row reads as "Admin" but a stripe_webhook one reads
// as "Stripe".
const PROVENANCE_META: Record<ProvenanceBucket, { label: string; hint: string }> = {
  tier_forced: { label: 'Bundle', hint: 'Always on for this tier — toggling here has no effect at read time.' },
  addon: { label: 'Add-on', hint: 'Granted by a purchased add-on subscription.' },
  custom_product: { label: 'Product', hint: 'Granted by an admin-composed custom product.' },
  paid_gate: { label: 'Paid gate', hint: "This tier's Stripe checkout gate." },
  tier_preset: { label: 'Signup', hint: 'Granted at signup for this tier — admin-toggleable.' },
  audit: { label: 'Admin', hint: 'Traced to a specific write — see the audit log.' },
  admin_grant: {
    label: 'Admin',
    hint: 'No plan, add-on, or product explains this — an admin (or broker, at creation) granted it directly. Actor is unrecorded (predates the write audit log). Use Manage to classify why.',
  },
}

// `bucket: 'audit'` covers 4 sources with different meanings — an admin
// manually flipping a toggle reads very differently from a Stripe webhook
// write, even though both are "traced" in the strict sense.
const AUDIT_SOURCE_LABELS: Record<string, string> = {
  admin_toggle: 'Admin',
  tier_change: 'Tier change',
  product_sync: 'Product sync',
  stripe_webhook: 'Stripe',
}

function provenanceLabel(entry: ProvenanceEntry): string {
  if (entry.bucket === 'audit' && entry.detail && typeof entry.detail === 'object') {
    return AUDIT_SOURCE_LABELS[entry.detail.source] ?? PROVENANCE_META.audit.label
  }
  return PROVENANCE_META[entry.bucket].label
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
  const { data: flagStatuses, reload: reloadFlagStatuses } = useAsync(
    () => api.get<FeatureFlagStatus[]>('/admin/feature-flags'),
    [],
    [],
  )
  // Built-in tier compositions (forced_on/forced_off from TIER_REQUIRED_FEATURES),
  // needed to detect a tier-forced-OFF flag — `provenance.features` only lists
  // currently-ENABLED features, so it can never surface a forced-off entry.
  const { data: builtinTiers } = useAsync(
    () => api.get<{ builtin_products: BuiltinTierComposition[] }>('/admin/products')
      .then((r) => r.builtin_products),
    [],
    [] as BuiltinTierComposition[],
  )
  const forcedOffByTier = useMemo(
    () => new Map(builtinTiers.map((t) => [t.slug, new Set(t.forced_off)])),
    [builtinTiers],
  )
  const [betaModalOpen, setBetaModalOpen] = useState(false)
  const [grantsModalOpen, setGrantsModalOpen] = useState(false)
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

  const { data: provenance, reload: reloadProvenance, setData: setProvenance } = useAsync(
    () => (selected
      ? api.get<ProvenanceResponse>(`/admin/company-features/${selected.id}/provenance`)
      : Promise.resolve(EMPTY_PROVENANCE)),
    [selected?.id],
    EMPTY_PROVENANCE,
  )
  // useAsync deliberately doesn't clear `data` on a reload (see its docstring)
  // so a filter/search re-render doesn't flash empty — but that means
  // switching the selected company here left `provenance` describing the
  // PREVIOUS company until the new fetch landed: wrong badges, wrongly
  // disabled toggles, and GrantsModal could PUT the old company's grant onto
  // the new one. Clear explicitly on identity change instead of relying on
  // the shared hook's reload semantics.
  const prevSelectedIdRef = useRef<string | null>(null)
  useEffect(() => {
    if (selected?.id !== prevSelectedIdRef.current) {
      prevSelectedIdRef.current = selected?.id ?? null
      setProvenance(EMPTY_PROVENANCE)
    }
  }, [selected?.id, setProvenance])
  // Flags this tier forces OFF at read time — `provenance.features` only
  // covers currently-ENABLED features, so a forced-off flag never appears
  // there and `tierForced` below must be computed from this set too, or the
  // toggle stays switchable and turning it "on" silently does nothing.
  const selectedForcedOff = useMemo(
    () => (provenance.plan.kind === 'builtin' && provenance.plan.slug
      ? forcedOffByTier.get(provenance.plan.slug) ?? new Set<string>()
      : new Set<string>()),
    [provenance.plan, forcedOffByTier],
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
      if (companyId === selected?.id) {
        await reloadProvenance()
      }
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
          <h1 className="flex-1 text-sm font-semibold text-zinc-100">Features</h1>
          <Button size="sm" variant="secondary" onClick={() => setBetaModalOpen(true)}>
            <Settings2 className="h-3.5 w-3.5" /> Manage beta
          </Button>
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
                  outsidePlanEntries.map(([key, p]) => {
                    const grant = provenance.grants[key]
                    return (
                      <span
                        key={key}
                        title={grant?.note || PROVENANCE_META[p.bucket].hint}
                        className="flex items-center gap-1 rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-0.5 text-[11px] text-zinc-300"
                      >
                        {FEATURE_LABELS[key] ?? key}
                        <span className="text-zinc-600">
                          · {grant ? GRANT_TYPE_LABELS[grant.grant_type] ?? grant.grant_type : provenanceLabel(p)}
                        </span>
                      </span>
                    )
                  })
                )}
                {outsidePlanEntries.length > 0 && (
                  <Button size="sm" variant="secondary" onClick={() => setGrantsModalOpen(true)}>
                    Manage
                  </Button>
                )}
              </div>
            </div>
            {Object.values(provenance.features).some((p) => p.bucket === 'admin_grant') && (
              <p className="border-b border-white/[0.06] bg-white/[0.02] px-4 py-1.5 text-[11px] text-zinc-500">
                Some enabled features are tagged "Admin" with no recorded actor — they predate
                the write audit log (feataudit01) or came from a path it doesn't yet cover.
                Use Manage above to classify why (comped, invoiced, trial, internal).
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
                      const forcedOff = !on && selectedForcedOff.has(key)
                      const provLabel = prov ? provenanceLabel(prov) : undefined
                      const provHint = prov
                        ? PROVENANCE_META[prov.bucket].hint
                        : forcedOff
                          ? 'Always off for this tier — toggling here has no effect at read time.'
                          : undefined
                      // A tier-forced flag (on OR off) is re-forced by
                      // merge_company_features on every read regardless of
                      // what's stored — toggling it here is a no-op at read
                      // time, so don't offer a toggle that lies.
                      const tierForced = prov?.bucket === 'tier_forced' || forcedOff
                      // A flag that needs another flag on first (huume needs
                      // matcha_work) — only blocks turning it ON; already-on
                      // stays togglable off. Mirrors backend
                      // assert_feature_dependencies, which is the real gate.
                      const missingPrereqs = !on
                        ? (FEATURE_REQUIRES[key] ?? []).filter((r) => !selected.enabled_features[r])
                        : []
                      const missingPrereq = missingPrereqs.length > 0
                      // The reverse direction: this key is itself a
                      // prerequisite (e.g. matcha_work for huume) — block
                      // turning it OFF while a dependent is still on, same
                      // as the backend would reject it.
                      const blockingDependents = on
                        ? Object.entries(FEATURE_REQUIRES)
                            .filter(([dep, reqs]) => reqs.includes(key) && !!selected.enabled_features[dep])
                            .map(([dep]) => dep)
                        : []
                      const blockedByDependent = blockingDependents.length > 0
                      const title = lockedOn
                        ? `${FEATURE_LABELS[key]} — beta, test accounts only`
                        : missingPrereq
                          ? `${FEATURE_LABELS[key]} — needs ${missingPrereqs.map((r) => FEATURE_LABELS[r] ?? r).join(', ')} enabled first`
                          : blockedByDependent
                            ? `${FEATURE_LABELS[key]} — disable ${blockingDependents.map((r) => FEATURE_LABELS[r] ?? r).join(', ')} first`
                            : provHint
                              ? `${FEATURE_LABELS[key]} — ${provHint}`
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
                            {provLabel && (
                              <Badge variant="neutral" className="shrink-0">{provLabel}</Badge>
                            )}
                          </span>
                          <Toggle
                            checked={on}
                            disabled={busy || lockedOn || tierForced || missingPrereq || blockedByDependent}
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

      {grantsModalOpen && selected && (
        <GrantsModal
          company={selected}
          entries={outsidePlanEntries}
          provenance={provenance}
          onClose={() => setGrantsModalOpen(false)}
          onSaved={reloadProvenance}
        />
      )}
      {betaModalOpen && (
        <BetaManageModal
          flagStatuses={flagStatuses}
          onClose={() => setBetaModalOpen(false)}
          onSaved={reloadFlagStatuses}
        />
      )}
    </div>
  )
}

function GrantsModal({
  company, entries, provenance, onClose, onSaved,
}: {
  company: CompanyFeatures
  entries: [string, ProvenanceEntry][]
  provenance: ProvenanceResponse
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { toast } = useToast()
  const [drafts, setDrafts] = useState<Record<string, { grant_type: string; note: string }>>(() =>
    Object.fromEntries(
      entries.map(([key]) => {
        const grant = provenance.grants[key]
        return [key, { grant_type: grant?.grant_type ?? '', note: grant?.note ?? '' }]
      })
    )
  )
  const [saving, setSaving] = useState<string | null>(null)

  const typeOptions = provenance.grant_types.map((t) => ({
    value: t, label: GRANT_TYPE_LABELS[t] ?? t,
  }))

  async function save(key: string) {
    const draft = drafts[key]
    if (!draft?.grant_type) return
    setSaving(key)
    try {
      await api.put(`/admin/company-features/${company.id}/grants/${key}`, {
        grant_type: draft.grant_type,
        note: (draft.note ?? '').trim() || null,
      })
      await onSaved()
      toast(`${FEATURE_LABELS[key] ?? key} classified as ${GRANT_TYPE_LABELS[draft.grant_type] ?? draft.grant_type}`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Save failed', 'error')
    } finally {
      setSaving(null)
    }
  }

  return (
    <Modal open onClose={onClose} title={`Manage grants — ${company.company_name}`} width="lg">
      <div className="space-y-4">
        <p className="text-xs text-zinc-500">
          Classify why each out-of-plan feature was given — separate from provenance, which only
          says where the flag came from.
        </p>
        {entries.map(([key, p]) => {
          const draft = drafts[key] ?? { grant_type: '', note: '' }
          return (
            <div key={key} className="grid grid-cols-[1fr_140px_1fr_auto] items-end gap-2 border-b border-white/[0.06] pb-3">
              <div className="text-[13px] text-zinc-300">
                {FEATURE_LABELS[key] ?? key}
                <p className="text-[11px] text-zinc-600">{provenanceLabel(p)}</p>
              </div>
              <Select
                label="Type"
                options={typeOptions}
                value={draft.grant_type}
                placeholder="Unclassified"
                onChange={(e) => setDrafts((d) => ({
                  ...d,
                  [key]: { ...(d[key] ?? { grant_type: '', note: '' }), grant_type: e.target.value },
                }))}
              />
              <Input
                label="Note"
                value={draft.note}
                onChange={(e) => setDrafts((d) => ({
                  ...d,
                  [key]: { ...(d[key] ?? { grant_type: '', note: '' }), note: e.target.value },
                }))}
                placeholder="Why / context"
              />
              <Button size="sm" disabled={saving === key || !draft.grant_type} onClick={() => save(key)}>
                {saving === key ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Save'}
              </Button>
            </div>
          )
        })}
      </div>
    </Modal>
  )
}

function BetaManageModal({
  flagStatuses, onClose, onSaved,
}: {
  flagStatuses: FeatureFlagStatus[]
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const { toast } = useToast()
  const [toggling, setToggling] = useState<string | null>(null)
  const byKey = useMemo(
    () => Object.fromEntries(flagStatuses.map((f) => [f.key, f])),
    [flagStatuses],
  )

  async function setBeta(key: string, isBeta: boolean) {
    setToggling(key)
    try {
      await api.patch(`/admin/feature-flags/${key}`, { is_beta: isBeta })
      await onSaved()
      toast(`${FEATURE_LABELS[key] ?? key} moved to ${isBeta ? 'beta' : 'ready'}`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Update failed', 'error')
    } finally {
      setToggling(null)
    }
  }

  return (
    <Modal open onClose={onClose} title="Manage beta status" width="lg">
      <div className="max-h-[70vh] space-y-5 overflow-y-auto">
        <p className="text-xs text-zinc-500">
          A beta feature can only be enabled for test companies. Moving it to ready here writes
          an admin override — no deploy needed; the code default in `feature_flags.BETA_FEATURES`
          is unaffected.
        </p>
        {FEATURE_GROUPS.map((group) => (
          <div key={group.label}>
            <div className={`mb-2 ${LABEL}`}>{group.label}</div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-5 gap-y-2">
              {Object.keys(group.features).map((key) => {
                const status = byKey[key]
                if (!status) return null
                return (
                  <div key={key} className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate text-xs text-zinc-400" title={FEATURE_LABELS[key]}>
                      {FEATURE_LABELS[key]}
                      {status.is_beta && status.non_test_enabled_count > 0 && (
                        <span className="ml-1.5 text-[10px] text-amber-400">
                          ({status.non_test_enabled_count} non-test enabled)
                        </span>
                      )}
                    </span>
                    <Toggle
                      checked={status.is_beta}
                      disabled={toggling === key}
                      onChange={(v) => setBeta(key, v)}
                      size="sm"
                    />
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  )
}
