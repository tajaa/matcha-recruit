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
      className="inline-flex items-center gap-2 px-5 h-10 rounded-md bg-emerald-500/90 hover:bg-emerald-500 text-zinc-950 text-sm font-medium disabled:opacity-50"
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
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Industry</FieldLabel>
          <select
            value={industry}
            onChange={(e) => { setIndustry(e.target.value); setSpecialty('') }}
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
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
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 disabled:opacity-50"
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
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Owner name</FieldLabel>
          <input
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
            placeholder="Jane Owner"
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
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
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 resize-y"
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
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Part-time</FieldLabel>
          <input
            type="number" min={0} value={pt}
            onChange={(e) => setPt(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Contractor</FieldLabel>
          <input
            type="number" min={0} value={contractor}
            onChange={(e) => setContractor(parseInt(e.target.value) || 0)}
            className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
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
          <div key={idx} className="rounded-md border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-3">
                <FieldLabel>Name</FieldLabel>
                <input
                  value={loc.name || ''}
                  onChange={(e) => update(idx, { name: e.target.value })}
                  placeholder="Main"
                  className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-3">
                <FieldLabel>City</FieldLabel>
                <input
                  value={loc.city || ''}
                  onChange={(e) => update(idx, { city: e.target.value })}
                  className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-2">
                <FieldLabel>State</FieldLabel>
                <select
                  value={loc.state || ''}
                  onChange={(e) => update(idx, { state: e.target.value })}
                  className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
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
                  className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
                />
              </div>
              <div className="col-span-1">
                <FieldLabel>Zip</FieldLabel>
                <input
                  value={loc.zipcode || ''}
                  onChange={(e) => update(idx, { zipcode: e.target.value })}
                  className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500"
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
          className="px-3 h-8 text-xs text-zinc-300 border border-zinc-700 rounded-md hover:border-zinc-500"
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

// ── Step 5: Gaps (existing vs missing + dispatch) ──────────────────────

function missingId(m: ResolvedScopeMissing): string {
  return [
    m.category_slug || '?',
    m.scope_level || '?',
    m.state || '-',
    m.county || '-',
    m.city || '-',
  ].join('::')
}

export function Step5Gaps({ session, onUpdated, onNext }: StepProps) {
  const [approved, setApproved] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [dispatchedCount, setDispatchedCount] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const resolved = session.resolved_scope
  const missing = resolved?.missing || []
  const existing = resolved?.existing || []

  function toggle(id: string) {
    setApproved((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function dispatchResearch() {
    setBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.dispatchResearch(session.id, Array.from(approved))
      setDispatchedCount(res.dispatched.length)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start research")
    } finally {
      setBusy(false)
    }
  }

  async function advance() {
    setBusy(true)
    setError(null)
    try {
      const updated = await adminOnboarding.patchSession(session.id, { step: 'review' })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not advance')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Coverage check</h2>
      <p className="text-sm text-zinc-400 mb-6">
        We already have data for {existing.length} of these requirement{existing.length === 1 ? '' : 's'}. {missing.length} {missing.length === 1 ? 'is' : 'are'} new — check the ones you want our background workers to research now. Anything you leave unchecked is skipped.
      </p>
      <ErrorBox message={error} />

      {existing.length > 0 && (
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-wider text-emerald-400 mb-1">
            Already covered · {existing.length}
          </div>
          <ul className="text-sm text-zinc-200 space-y-0.5 max-h-48 overflow-auto">
            {existing.map((e) => (
              <li key={e.requirement_id}>
                <span className="text-zinc-400">{e.category_slug}</span> · {e.title || e.canonical_key || e.requirement_id}
              </li>
            ))}
          </ul>
        </div>
      )}

      {missing.length > 0 && (
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-wider text-amber-400 mb-1">
            Needs research · {missing.length}
          </div>
          <ul className="text-sm text-zinc-200 space-y-1.5 max-h-72 overflow-auto">
            {missing.map((m) => {
              const id = missingId(m)
              return (
                <li key={id} className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={approved.has(id)}
                    onChange={() => toggle(id)}
                    className="mt-0.5"
                  />
                  <div>
                    <div>
                      <span className="text-zinc-400">{m.category_slug}</span>
                      {' · '}
                      <span className="text-zinc-300">{m.scope_level}</span>
                      {(m.state || m.county || m.city) && (
                        <span className="text-zinc-500"> · {[m.state, m.county, m.city].filter(Boolean).join(' / ')}</span>
                      )}
                    </div>
                    {m.reason && <div className="text-[11px] text-zinc-500">{m.reason}</div>}
                  </div>
                </li>
              )
            })}
          </ul>
          {dispatchedCount !== null && (
            <div className="mt-2 text-xs text-emerald-300">
              {dispatchedCount} research job{dispatchedCount === 1 ? '' : 's'} started in the background. They'll write to our compliance database when finished.
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        {missing.length > 0 && (
          <button
            onClick={() => void dispatchResearch()}
            disabled={busy || approved.size === 0}
            className="inline-flex items-center gap-2 px-4 h-10 rounded-md bg-amber-500/90 hover:bg-amber-500 text-zinc-950 text-sm font-medium disabled:opacity-50"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            Start research ({approved.size})
          </button>
        )}
        <PrimaryButton busy={busy} onClick={() => void advance()}>
          Continue to review
        </PrimaryButton>
      </div>
    </div>
  )
}

// ── Step 6: Review + Finalize ──────────────────────────────────────────

export function Step6Review({ session, onUpdated }: StepProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [gapBusy, setGapBusy] = useState(false)
  const [gap, setGap] = useState<GapCheckResult | null>(
    (session.resolved_scope as unknown as { gap_check?: GapCheckResult } | null)?.gap_check ?? null,
  )
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

  const basics = session.basics
  const resolved = session.resolved_scope
  const ai = session.ai_scope

  const totalSuggestions =
    (gap?.suggested_compliance_categories.length ?? 0) +
    (gap?.suggested_certifications.length ?? 0) +
    (gap?.suggested_licenses.length ?? 0) +
    (gap?.suggested_jurisdictions.length ?? 0)

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Review + Finalize</h2>
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

      <div className="mt-6 mb-6 rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="text-sm text-zinc-100 font-medium">Final gap check</div>
            <div className="text-xs text-zinc-500">
              Gemini re-reads everything captured and flags anything the wizard missed. Read-only — Finalize is still up to you.
            </div>
          </div>
          <button
            onClick={() => void runGapCheck()}
            disabled={gapBusy}
            className="inline-flex items-center gap-2 px-3 h-8 rounded-md border border-zinc-700 hover:border-zinc-500 text-xs text-zinc-200 disabled:opacity-50"
          >
            {gapBusy && <Loader2 className="w-3 h-3 animate-spin" />}
            {gap ? 'Re-run gap check' : 'Run gap check'}
          </button>
        </div>
        {gap && <GapPanel gap={gap} totalSuggestions={totalSuggestions} />}
      </div>

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
                to={`/admin/onboarding/${session.id}/report`}
                className="text-sm text-emerald-300 hover:underline font-medium"
              >
                View full gap analysis →
              </Link>
            </div>
          </div>
        ) : (
          <>
            <PrimaryButton busy={busy} onClick={() => void finalize()}>
              Finalize onboarding
            </PrimaryButton>
            {gap && totalSuggestions > 0 && (
              <p className="mt-2 text-[11px] text-amber-300">
                Gap check surfaced {totalSuggestions} item{totalSuggestions === 1 ? '' : 's'}. Re-run Step 4 expand to fold them in, or finalize and address from the company compliance page later.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function GapPanel({ gap, totalSuggestions }: { gap: GapCheckResult; totalSuggestions: number }) {
  if (totalSuggestions === 0) {
    return (
      <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-200">
        <div className="font-medium">Manifest looks comprehensive.</div>
        {gap.summary && <div className="text-xs text-emerald-300/80 mt-0.5">{gap.summary}</div>}
      </div>
    )
  }
  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-100 space-y-3">
      {gap.summary && <div className="text-xs text-amber-200">{gap.summary}</div>}
      <SuggestionList title="Compliance categories" items={gap.suggested_compliance_categories.map((c) => ({
        head: `${c.category_slug} · ${c.scope}`,
        reason: c.reason || undefined,
      }))} />
      <SuggestionList title="Certifications" items={gap.suggested_certifications.map((c) => ({
        head: c.name,
        reason: c.reason || undefined,
      }))} />
      <SuggestionList title="Licenses" items={gap.suggested_licenses.map((l) => ({
        head: l.name,
        reason: l.reason || undefined,
      }))} />
      <SuggestionList title="Jurisdictions" items={gap.suggested_jurisdictions.map((j) => ({
        head: [j.state, j.county, j.city].filter(Boolean).join(' / ') || '(federal)',
        reason: j.reason || undefined,
      }))} />
    </div>
  )
}

function SuggestionList({
  title,
  items,
}: {
  title: string
  items: { head: string; reason?: string }[]
}) {
  if (items.length === 0) return null
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-amber-300 mb-1">{title}</div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i}>
            <div className="text-zinc-100">• {it.head}</div>
            {it.reason && <div className="text-[11px] text-zinc-400 ml-3">{it.reason}</div>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-4 py-1.5 border-b border-zinc-800 last:border-b-0">
      <div className="w-44 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-200">{value}</div>
    </div>
  )
}
