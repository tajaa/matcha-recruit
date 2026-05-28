/**
 * Six wizard steps for the master-admin onboarding flow. Co-located in
 * one file because they share the same session-detail prop shape and
 * the steps are deliberately thin (the heavy lifting lives in the
 * backend `/expand` + `/resolve` endpoints). Splitting per-file would
 * mostly multiply boilerplate.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import {
  adminOnboarding,
  type AIScope,
  type BasicsPayload,
  type GapCheckResult,
  type LocationInput,
  type OnboardingSessionDetail,
  type ResolvedScopeMissing,
  type SizePayload,
} from '../../api/adminOnboarding'

// True when the AI scope expansion came back essentially blank — no
// NAICS sector and no items in any of the four lists. Means Gemini
// either refused to infer or returned malformed JSON that fell back
// to the route's empty-AIScope() default. Frontend uses this to swap
// the "Check our database" CTA for a "re-run expansion" prompt.
function isScopeEmpty(s: AIScope | null | undefined): boolean {
  if (!s) return true
  return (
    !s.naics_sector
    && (s.compliance_categories?.length || 0) === 0
    && (s.required_certifications?.length || 0) === 0
    && (s.required_licenses?.length || 0) === 0
    && (s.applicable_jurisdictions?.length || 0) === 0
  )
}

// ── Shared ──────────────────────────────────────────────────────────────

type StepProps = {
  session: OnboardingSessionDetail
  onUpdated: (s: OnboardingSessionDetail) => void
  onNext: () => void
}

const ALL_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM',
  'NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA',
  'WV','WI','WY',
]

function PrimaryButton({
  busy,
  children,
  disabled,
  onClick,
}: {
  busy?: boolean
  children: React.ReactNode
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      className="inline-flex items-center gap-2 px-5 h-10 rounded-md bg-vsc-accent text-vsc-bg hover:opacity-90 text-sm font-medium disabled:opacity-50"
    >
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[11px] uppercase tracking-wider text-zinc-400 mb-1">
      {children}
    </label>
  )
}

function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300 mb-4">
      {message}
    </div>
  )
}

// ── Step 1: Basics ──────────────────────────────────────────────────────

export function Step1Basics({ session, onUpdated, onNext }: StepProps) {
  const [specialties, setSpecialties] = useState<Record<string, string[]>>({})
  const [businessName, setBusinessName] = useState(session.basics.business_name || '')
  const [industry, setIndustry] = useState(session.basics.industry || '')
  const [specialty, setSpecialty] = useState(session.basics.specialty || '')
  const [description, setDescription] = useState(session.basics.description || '')
  const [ownerEmail, setOwnerEmail] = useState(session.basics.owner_email || '')
  const [ownerName, setOwnerName] = useState(session.basics.owner_name || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void adminOnboarding.specialties().then(setSpecialties).catch(() => undefined)
  }, [])

  const industryOptions = useMemo(() => Object.keys(specialties).sort(), [specialties])
  const specialtyOptions = specialties[industry] || []
  const valid = businessName.trim() && industry && ownerEmail.includes('@')

  async function save() {
    if (!valid || busy) return
    setBusy(true)
    setError(null)
    try {
      const payload: BasicsPayload = {
        business_name: businessName.trim(),
        industry,
        specialty: specialty || null,
        description: description.trim() || null,
        owner_email: ownerEmail.trim(),
        owner_name: ownerName.trim() || null,
      }
      const updated = await adminOnboarding.patchSession(session.id, {
        basics: payload,
        step: 'size',
      })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Business basics</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Name, industry, sub-specialty, and the owner email we'll invite at the end.
      </p>
      <ErrorBox message={error} />

      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <FieldLabel>Business name</FieldLabel>
          <input
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            placeholder="Acme Diner"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Industry</FieldLabel>
          <select
            value={industry}
            onChange={(e) => { setIndustry(e.target.value); setSpecialty('') }}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          >
            <option value="">— pick —</option>
            {industryOptions.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel>Specialty</FieldLabel>
          <select
            value={specialty}
            onChange={(e) => setSpecialty(e.target.value)}
            disabled={specialtyOptions.length === 0}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 disabled:opacity-50"
          >
            <option value="">{specialtyOptions.length ? '— optional —' : '— none —'}</option>
            {specialtyOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel>Owner email</FieldLabel>
          <input
            type="email"
            value={ownerEmail}
            onChange={(e) => setOwnerEmail(e.target.value)}
            placeholder="owner@example.com"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Owner name</FieldLabel>
          <input
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
            placeholder="Jane Owner"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div className="col-span-2">
          <FieldLabel>
            Company description
            <span className="ml-2 normal-case tracking-normal text-zinc-500">
              · the AI uses this to find non-obvious requirements
            </span>
          </FieldLabel>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            maxLength={2000}
            placeholder={
              'What does this company actually do? Who works here ' +
              '(grad students, contractors, minors)? Notable activities, ' +
              'facilities, services, hours, hazards? Be specific — examples: ' +
              '"BSL-2 lab handling human tissue samples; 8 UCSF grad students ' +
              'on rotation; late-night work; no minors" or "full-service ' +
              'restaurant with bar; tipped staff; live music Fri/Sat past ' +
              'midnight; outdoor patio with heaters". The more detail, the ' +
              'better the AI can surface compliance the HR admin might miss.'
            }
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 resize-y"
          />
          <div className="text-[11px] text-zinc-500 mt-1">
            {description.length} / 2000
          </div>
        </div>
      </div>

      <div className="mt-6">
        <PrimaryButton busy={busy} disabled={!valid} onClick={() => void save()}>
          Save + Continue
        </PrimaryButton>
      </div>
    </div>
  )
}

// ── Step 2: Size ────────────────────────────────────────────────────────

export function Step2Size({ session, onUpdated, onNext }: StepProps) {
  const initial = session.size as Partial<SizePayload>
  const [ft, setFt] = useState(initial.full_time ?? 0)
  const [pt, setPt] = useState(initial.part_time ?? 0)
  const [contractor, setContractor] = useState(initial.contractor ?? 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(source: SizePayload['source']) {
    setBusy(true)
    setError(null)
    try {
      const payload: SizePayload = {
        full_time: ft,
        part_time: pt,
        contractor,
        unknown: 0,
        source,
      }
      const updated = await adminOnboarding.patchSession(session.id, {
        size: payload,
        step: 'locations',
      })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Headcount</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Rough totals. Full HRIS / employee import is Phase 2 — we just need ballpark counts for scope decisions.
      </p>
      <ErrorBox message={error} />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <FieldLabel>Full-time</FieldLabel>
          <input
            type="number" min={0} value={ft}
            onChange={(e) => setFt(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Part-time</FieldLabel>
          <input
            type="number" min={0} value={pt}
            onChange={(e) => setPt(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Contractor</FieldLabel>
          <input
            type="number" min={0} value={contractor}
            onChange={(e) => setContractor(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <PrimaryButton busy={busy} onClick={() => void save('manual')}>
          Save + Continue
        </PrimaryButton>
        <button
          onClick={() => void save('skipped')}
          disabled={busy}
          className="px-4 h-10 text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    </div>
  )
}

// ── Step 3: Locations + create-company ─────────────────────────────────

export function Step3Locations({ session, onUpdated, onNext }: StepProps) {
  const [locations, setLocations] = useState<LocationInput[]>(
    session.locations.length ? session.locations : [{}],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function update(idx: number, patch: Partial<LocationInput>) {
    setLocations((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)))
  }
  function add() {
    setLocations((prev) => [...prev, {}])
  }
  function remove(idx: number) {
    setLocations((prev) => prev.filter((_, i) => i !== idx))
  }

  async function save() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const updated = await adminOnboarding.patchSession(session.id, {
        locations: { locations },
        step: 'scope',
      })
      // Provision the company + sentinel + per-location rows.
      await adminOnboarding.createCompany(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
      // Step 3 ends with provisioning; advancing leads into Step 4 (scope).
      onNext()
      return updated
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Locations</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Add each physical location. State drives jurisdiction-specific scope. County / city refine it. A company-wide sentinel is added automatically for federal-only requirements.
      </p>
      <ErrorBox message={error} />

      <div className="space-y-3 mb-4">
        {locations.map((loc, idx) => (
          <div key={idx} className="rounded-md border border-vsc-border bg-vsc-panel p-3">
            <div className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-3">
                <FieldLabel>Name</FieldLabel>
                <input
                  value={loc.name || ''}
                  onChange={(e) => update(idx, { name: e.target.value })}
                  placeholder="Main"
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-3">
                <FieldLabel>City</FieldLabel>
                <input
                  value={loc.city || ''}
                  onChange={(e) => update(idx, { city: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-2">
                <FieldLabel>State</FieldLabel>
                <select
                  value={loc.state || ''}
                  onChange={(e) => update(idx, { state: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                >
                  <option value="">—</option>
                  {ALL_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <FieldLabel>County</FieldLabel>
                <input
                  value={loc.county || ''}
                  onChange={(e) => update(idx, { county: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-1">
                <FieldLabel>Zip</FieldLabel>
                <input
                  value={loc.zipcode || ''}
                  onChange={(e) => update(idx, { zipcode: e.target.value })}
                  className="w-full rounded-md bg-vsc-bg border border-vsc-border px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-1 flex justify-end">
                {locations.length > 1 && (
                  <button
                    onClick={() => remove(idx)}
                    className="text-zinc-500 hover:text-red-400 text-xs"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={add}
          className="px-3 h-8 text-xs text-zinc-300 border border-vsc-border rounded-md hover:border-zinc-500"
        >
          + Add location
        </button>
        <div className="ml-auto">
          <PrimaryButton busy={busy} onClick={() => void save()}>
            Save + Provision company
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

// ── Step 4: Scope (AI expand) ──────────────────────────────────────────

export function Step4Scope({ session, onUpdated, onNext }: StepProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scope = session.ai_scope

  async function expand() {
    setBusy(true)
    setError(null)
    try {
      await adminOnboarding.expand(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scope expansion failed')
    } finally {
      setBusy(false)
    }
  }

  async function resolve() {
    setBusy(true)
    setError(null)
    try {
      await adminOnboarding.resolve(session.id)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Coverage check failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">AI scope expansion</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Gemini reads industry + specialty + locations and proposes compliance categories, certifications, and licenses. Next you'll see which ones we already have data for and which need new research.
      </p>
      <ErrorBox message={error} />

      {!scope ? (
        <PrimaryButton busy={busy} onClick={() => void expand()}>
          Run AI scope expansion
        </PrimaryButton>
      ) : (
        <>
          <div className="mb-4 text-xs text-zinc-400">
            NAICS sector: <span className="text-zinc-200">{scope.naics_sector || '—'}</span>
          </div>
          <ScopeList title="Compliance categories" items={scope.compliance_categories.map((c) => `${c.category_slug} · ${c.scope}`)} />
          <ScopeList title="Certifications" items={scope.required_certifications.map((c) => c.name)} />
          <ScopeList title="Licenses" items={scope.required_licenses.map((l) => l.name)} />
          <ScopeList title="Applicable jurisdictions" items={scope.applicable_jurisdictions.map((j) => `${j.state || 'US'}${j.county ? ` · ${j.county}` : ''}${j.city ? ` · ${j.city}` : ''}`)} />

          {isScopeEmpty(scope) ? (
            <div className="mt-2 mb-4 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
              <div className="font-medium">AI couldn't infer scope from your inputs.</div>
              <div className="mt-1 text-amber-200/80">
                Try expanding the company description in Step 1 (industry, services, specialties) or re-run the expansion. If this keeps happening, the AI may be timing out.
              </div>
              <button
                onClick={() => void expand()}
                disabled={busy}
                className="mt-3 inline-flex items-center gap-2 px-3 h-9 text-xs rounded bg-amber-500/90 hover:bg-amber-500 text-zinc-950 disabled:opacity-50"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Re-run AI scope expansion
              </button>
            </div>
          ) : (
            <div className="mt-6 flex items-center gap-2">
              <PrimaryButton busy={busy} onClick={() => void resolve()}>
                Check our database
              </PrimaryButton>
              <button
                onClick={() => void expand()}
                disabled={busy}
                className="px-3 h-9 text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-50"
              >
                Re-run AI expand
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ScopeList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mb-4">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">{title}</div>
      {items.length === 0 ? (
        <div className="text-sm text-zinc-600">— none —</div>
      ) : (
        <ul className="text-sm text-zinc-200 space-y-0.5">
          {items.map((i) => (
            <li key={i}>• {i}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Gap-analysis helpers (shared by Step 5) ────────────────────────────

function missingId(m: ResolvedScopeMissing): string {
  return [
    m.category_slug || '?',
    m.scope_level || '?',
    m.state || '-',
    m.county || '-',
    m.city || '-',
  ].join('::')
}

function jurisdictionKey(
  state?: string | null,
  county?: string | null,
  city?: string | null,
): string {
  return [state, county, city].filter(Boolean).join(' / ') || 'Federal'
}

function groupByKey<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const buckets = new Map<string, T[]>()
  for (const item of items) {
    const k = key(item)
    const arr = buckets.get(k)
    if (arr) arr.push(item)
    else buckets.set(k, [item])
  }
  return buckets
}

// ── Step 5: Gap Analysis (coverage + missing + AI safety net) ──────────

export function Step5GapAnalysis({ session, onUpdated, onNext }: StepProps) {
  const persistedGap =
    (session.resolved_scope as unknown as { gap_check?: GapCheckResult } | null)?.gap_check ?? null

  const [approved, setApproved] = useState<Set<string>>(new Set())
  const [dispatchBusy, setDispatchBusy] = useState(false)
  const [advanceBusy, setAdvanceBusy] = useState(false)
  const [dispatchedCount, setDispatchedCount] = useState<number | null>(null)
  const [gap, setGap] = useState<GapCheckResult | null>(persistedGap)
  const [gapBusy, setGapBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resolved = session.resolved_scope
  const missing = resolved?.missing || []
  const existing = resolved?.existing || []

  const missingByJurisdiction = useMemo(
    () => groupByKey(missing, (m) => jurisdictionKey(m.state, m.county, m.city)),
    [missing],
  )

  const existingByCategory = useMemo(
    () => groupByKey(existing, (e) => e.category_slug || 'other'),
    [existing],
  )

  const suggestedJurisdictionsByState = useMemo(() => {
    if (!gap) return new Map<string, GapCheckResult['suggested_jurisdictions']>()
    return groupByKey(gap.suggested_jurisdictions, (j) => j.state || 'Federal')
  }, [gap])

  const totalSuggestions = gap
    ? gap.suggested_compliance_categories.length +
      gap.suggested_certifications.length +
      gap.suggested_licenses.length +
      gap.suggested_jurisdictions.length
    : 0

  function toggle(id: string) {
    setApproved((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleBucket(ids: string[], allSelected: boolean) {
    setApproved((prev) => {
      const next = new Set(prev)
      if (allSelected) ids.forEach((id) => next.delete(id))
      else ids.forEach((id) => next.add(id))
      return next
    })
  }

  async function dispatchResearch() {
    setDispatchBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.dispatchResearch(session.id, Array.from(approved))
      setDispatchedCount(res.dispatched.length)
      setApproved(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start research")
    } finally {
      setDispatchBusy(false)
    }
  }

  async function runGapCheck() {
    setGapBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.gapCheck(session.id)
      setGap(res.gap_check)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gap check failed')
    } finally {
      setGapBusy(false)
    }
  }

  async function advance() {
    setAdvanceBusy(true)
    setError(null)
    try {
      const updated = await adminOnboarding.patchSession(session.id, { step: 'review' })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not advance')
    } finally {
      setAdvanceBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Gap Analysis</h2>
      <p className="text-sm text-zinc-400 mb-5">
        {missing.length} to research · {existing.length} already covered
        {gap ? ` · AI flagged ${totalSuggestions} extra${totalSuggestions === 1 ? '' : 's'}` : ''}
      </p>
      <ErrorBox message={error} />

      {/* Card A — Needs research (actionable) */}
      {missing.length > 0 ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4 mb-4">
          <div className="mb-3">
            <div className="text-sm font-medium text-amber-100">
              Needs research · {missing.length}
            </div>
            <div className="text-[11px] text-amber-200/70">
              Tick what to dispatch — background workers research and write to the compliance DB.
            </div>
          </div>

          <div className="space-y-3 max-h-[28rem] overflow-auto pr-1">
            {Array.from(missingByJurisdiction.entries()).map(([jKey, items]) => {
              const ids = items.map(missingId)
              const allSelected = ids.every((id) => approved.has(id))
              return (
                <div key={jKey}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-[11px] uppercase tracking-wider text-zinc-400">
                      {jKey} · {items.length}
                    </div>
                    <button
                      onClick={() => toggleBucket(ids, allSelected)}
                      className="text-[11px] text-amber-300 hover:text-amber-200"
                    >
                      {allSelected ? 'Clear' : 'Select all'}
                    </button>
                  </div>
                  <ul className="space-y-1.5">
                    {items.map((m) => {
                      const id = missingId(m)
                      return (
                        <li key={id} className="flex items-start gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={approved.has(id)}
                            onChange={() => toggle(id)}
                            className="mt-0.5"
                          />
                          <div className="min-w-0">
                            <div className="text-zinc-100">
                              {m.category_slug.replace(/_/g, ' ')}
                              <span className="text-zinc-500"> · {m.scope_level}</span>
                            </div>
                            {m.reason && (
                              <div className="text-[11px] text-zinc-400">{m.reason}</div>
                            )}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )
            })}
          </div>

          <div className="flex items-center gap-3 mt-4 pt-3 border-t border-amber-500/20">
            <button
              onClick={() => void dispatchResearch()}
              disabled={dispatchBusy || approved.size === 0}
              className="inline-flex items-center gap-2 px-4 h-9 rounded-md bg-amber-500/90 hover:bg-amber-500 text-zinc-950 text-sm font-medium disabled:opacity-50"
            >
              {dispatchBusy && <Loader2 className="w-4 h-4 animate-spin" />}
              Start research ({approved.size})
            </button>
            {dispatchedCount !== null && (
              <div className="text-xs text-emerald-300">
                {dispatchedCount} job{dispatchedCount === 1 ? '' : 's'} started — results land in the compliance DB.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-200 mb-4">
          Nothing new to research — every resolved requirement is already in the compliance DB.
        </div>
      )}

      {/* Card B — Already covered (informational, collapsed) */}
      {existing.length > 0 && (
        <details className="group rounded-md border border-vsc-border bg-vsc-panel p-4 mb-4">
          <summary className="cursor-pointer list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
            <div className="text-[11px] uppercase tracking-wider text-emerald-400">
              Already covered · {existing.length}
            </div>
            <span className="text-[11px] text-zinc-500 group-open:hidden">Show</span>
            <span className="text-[11px] text-zinc-500 hidden group-open:inline">Hide</span>
          </summary>
          <div className="mt-3 space-y-3 max-h-72 overflow-auto pr-1">
            {Array.from(existingByCategory.entries()).map(([cat, items]) => (
              <div key={cat}>
                <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">
                  {cat.replace(/_/g, ' ')} · {items.length}
                </div>
                <ul className="text-sm text-zinc-300 space-y-0.5">
                  {items.map((e) => (
                    <li key={e.requirement_id}>
                      • {e.title || e.canonical_key || e.requirement_id}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Card C — AI safety net (read-only suggestion) */}
      <div className="rounded-md border border-vsc-border bg-vsc-panel p-4 mb-6">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <div className="text-sm font-medium text-zinc-100">AI safety net</div>
            <div className="text-[11px] text-zinc-500">
              Gemini re-reads the manifest and flags anything the wizard missed. Read-only — Finalize on the next step.
            </div>
          </div>
          <button
            onClick={() => void runGapCheck()}
            disabled={gapBusy}
            className="inline-flex items-center gap-2 px-3 h-8 rounded-md border border-vsc-border hover:border-zinc-500 text-xs text-zinc-200 disabled:opacity-50 shrink-0"
          >
            {gapBusy && <Loader2 className="w-3 h-3 animate-spin" />}
            {gap ? 'Re-run' : 'Run gap check'}
          </button>
        </div>

        {gap && totalSuggestions === 0 && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-200 mt-3">
            <div className="font-medium">Manifest looks comprehensive.</div>
            {gap.summary && (
              <div className="text-xs text-emerald-300/80 mt-0.5">{gap.summary}</div>
            )}
          </div>
        )}

        {gap && totalSuggestions > 0 && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 space-y-4 mt-3">
            {gap.summary && <div className="text-xs text-amber-200">{gap.summary}</div>}

            {gap.suggested_jurisdictions.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-amber-300 mb-1">
                  New jurisdictions to track
                </div>
                <div className="space-y-2">
                  {Array.from(suggestedJurisdictionsByState.entries()).map(([state, items]) => (
                    <div key={state}>
                      <div className="text-[11px] text-zinc-400">{state}</div>
                      <ul className="text-sm text-zinc-100 space-y-0.5 ml-2">
                        {items.map((j, i) => (
                          <li key={i}>
                            • {jurisdictionKey(j.state, j.county, j.city)}
                            {j.reason && (
                              <div className="text-[11px] text-zinc-400 ml-3">{j.reason}</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(gap.suggested_compliance_categories.length > 0 ||
              gap.suggested_certifications.length > 0 ||
              gap.suggested_licenses.length > 0) && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-amber-300 mb-1">
                  Items to add to manifest
                </div>
                <ul className="text-sm text-zinc-100 space-y-1.5">
                  {gap.suggested_compliance_categories.map((c, i) => (
                    <li key={`c-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        Category
                      </span>
                      {c.category_slug.replace(/_/g, ' ')}
                      <span className="text-zinc-500"> · {c.scope}</span>
                      {c.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{c.reason}</div>
                      )}
                    </li>
                  ))}
                  {gap.suggested_certifications.map((c, i) => (
                    <li key={`cert-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        Cert
                      </span>
                      {c.name}
                      {c.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{c.reason}</div>
                      )}
                    </li>
                  ))}
                  {gap.suggested_licenses.map((l, i) => (
                    <li key={`lic-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        License
                      </span>
                      {l.name}
                      {l.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{l.reason}</div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <PrimaryButton busy={advanceBusy} onClick={() => void advance()}>
          Continue to Finalize
        </PrimaryButton>
        {gap && totalSuggestions > 0 && (
          <span className="text-[11px] text-amber-300">
            {totalSuggestions} suggestion{totalSuggestions === 1 ? '' : 's'} flagged — re-run earlier steps to fold them in, or finalize and address from the company compliance page later.
          </span>
        )}
      </div>
    </div>
  )
}

// ── Step 6: Finalize ───────────────────────────────────────────────────

export function Step6Review({ session, onUpdated }: StepProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finalized, setFinalized] = useState<{
    company_id: string
    invite_token?: string | null
    scope_rows_written: number
    certifications_written: number
    licenses_written: number
  } | null>(null)

  async function finalize() {
    setBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.finalize(session.id)
      setFinalized(res)
      const refreshed = await adminOnboarding.getSession(session.id)
      onUpdated(refreshed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Finalize failed')
    } finally {
      setBusy(false)
    }
  }

  const basics = session.basics
  const resolved = session.resolved_scope
  const ai = session.ai_scope

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Finalize</h2>
      <p className="text-sm text-zinc-400 mb-6">
        One last look before we write the scope manifest and issue the owner invite.
      </p>
      <ErrorBox message={error} />

      <SummaryRow label="Business" value={basics.business_name || '—'} />
      <SummaryRow label="Industry" value={`${basics.industry || '—'}${basics.specialty ? ` · ${basics.specialty}` : ''}`} />
      <SummaryRow label="Owner" value={basics.owner_email || '—'} />
      <SummaryRow label="Locations" value={`${session.locations.length} location${session.locations.length === 1 ? '' : 's'}`} />
      <SummaryRow label="Already covered" value={`${resolved?.existing.length ?? 0}`} />
      <SummaryRow label="Certifications" value={`${ai?.required_certifications.length ?? 0}`} />
      <SummaryRow label="Licenses" value={`${ai?.required_licenses.length ?? 0}`} />

      <div className="mt-6">
        {finalized ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-200 space-y-1">
            <div className="font-medium">Gap analysis finalized.</div>
            <div>Scope rows written: {finalized.scope_rows_written}</div>
            <div>Certifications: {finalized.certifications_written} · Licenses: {finalized.licenses_written}</div>
            {finalized.invite_token && (
              <div className="pt-2 border-t border-emerald-500/20">
                <div className="text-[11px] uppercase tracking-wider text-emerald-300 mb-0.5">
                  Owner invite token
                </div>
                <code className="text-xs text-zinc-100 break-all">{finalized.invite_token}</code>
              </div>
            )}
            <div className="pt-2 border-t border-emerald-500/20">
              <Link
                to={`/admin/gap-analysis/${session.id}/report`}
                className="text-sm text-emerald-300 hover:underline font-medium"
              >
                View full gap analysis →
              </Link>
            </div>
          </div>
        ) : (
          <PrimaryButton busy={busy} onClick={() => void finalize()}>
            Finalize onboarding
          </PrimaryButton>
        )}
      </div>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-4 py-1.5 border-b border-vsc-border last:border-b-0">
      <div className="w-44 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-200">{value}</div>
    </div>
  )
}
