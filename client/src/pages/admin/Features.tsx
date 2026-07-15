import { useEffect, useMemo, useState } from 'react'
import { ToggleLeft, Search, Loader2 } from 'lucide-react'
import { Badge, Toggle, LABEL } from '../../components/ui'
import { api } from '../../api/client'

const FEATURE_GROUPS: { label: string; features: Record<string, string> }[] = [
  {
    label: 'Core HR',
    features: {
      policies: 'Policies',
      handbooks: 'Handbooks',
      compliance: 'Compliance',
      employees: 'Employees',
      offer_letters: 'Offer Letters',
      er_copilot: 'ER Copilot',
      incidents: 'Incidents',
      time_off: 'Time Off',
      accommodations: 'Accommodations',
      interview_prep: 'Interview Prep',
      risk_assessment: 'Risk Assessment',
      training: 'Training',
      i9: 'I-9 Verification',
      cobra: 'COBRA',
      separation_agreements: 'Separation Agreements',
      credential_templates: 'Credential Templates',
      discipline: 'Performance Action',
      employee_schedule: 'Employee Schedule (shift scheduling — assignments, templates, swap/drop requests)',
    },
  },
  {
    label: 'HRIS',
    features: {
      hris_gusto: 'HRIS — Gusto (direct)',
      hris_finch: 'HRIS — Finch (Rippling, BambooHR, ADP…)',
      hris_deductions: 'HRIS — Deductions/benefits write (Finch)',
      hris_import: 'HRIS Import (legacy — enables both)',
    },
  },
  {
    label: 'Matcha Work',
    features: {
      matcha_work: 'Matcha Work',
      inventory: 'Inventory',
      werk_lite: 'Werk Lite (work-chat surface — needs Matcha Work too)',
      werk_lite_calls_all_members: 'Werk Lite — any member can start calls',
      hr_pilot: 'HR Pilot (thread mode — handbook-grounded supervisor guidance + hard-stop HR escalation gate)',
    },
  },
  {
    label: 'Risk & Underwriting',
    features: {
      workforce_compliance: 'Workforce Compliance (pay transparency · AI-audit · biometric)',
      risk_profile: 'Risk Profile (client-facing composite risk index)',
      resident_care: 'Resident-Care Risk (healthcare/senior-living asset)',
      controls_evidence: 'Proof of Controls (controls-evidence register + packet)',
      limit_adequacy: 'Limit Adequacy & Contract Review (limits vs contracts)',
      driver_risk: 'Driver Risk (fleet MVR scoring — commercial auto)',
    },
  },
  {
    label: 'AI Pilots',
    features: {
      ir_voice_intake: 'IR Voice Intake (dictate on create + magic-link forms)',
      legal_defense: 'Legal Pilot (AI litigation-evidence packets)',
      handbook_pilot: 'Handbook Pilot (AI handbook/policy generation)',
      analysis_pilot: 'Analysis Pilot (general data-analysis chat — CSV/XLSX/PDF, deterministic metrics)',
    },
  },
]

const FEATURE_LABELS: Record<string, string> = Object.fromEntries(
  FEATURE_GROUPS.flatMap((g) => Object.entries(g.features))
)
const FEATURE_KEYS = Object.keys(FEATURE_LABELS)

type CompanyFeatures = {
  id: string
  company_name: string
  enabled_features: Record<string, boolean>
}

function enabledCount(features: Record<string, boolean>) {
  return FEATURE_KEYS.filter((k) => features[k]).length
}

export default function Features() {
  const [companies, setCompanies] = useState<CompanyFeatures[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    api.get<CompanyFeatures[]>('/admin/company-features')
      .then(setCompanies)
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(
    () => companies.filter((c) => c.company_name.toLowerCase().includes(search.toLowerCase())),
    [companies, search]
  )

  // Auto-select the first visible row so the detail pane is never empty when
  // there's something to show, and drop the selection once it scrolls out of
  // the filtered list.
  const selected = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null

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
    <div className="flex h-[calc(100vh-7rem)] overflow-hidden rounded-xl border border-white/[0.06] bg-black">
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
              <h2 className="text-sm font-semibold text-zinc-100">{selected.company_name}</h2>
              <Badge variant={enabledCount(selected.enabled_features) > 0 ? 'success' : 'neutral'}>
                {enabledCount(selected.enabled_features)}/{FEATURE_KEYS.length} enabled
              </Badge>
            </div>
            <div className="flex-1 space-y-5 overflow-y-auto p-4">
              {FEATURE_GROUPS.map((group) => (
                <div key={group.label}>
                  <div className={`mb-2 ${LABEL}`}>{group.label}</div>
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-5 gap-y-3">
                    {Object.keys(group.features).map((key) => {
                      const on = !!selected.enabled_features[key]
                      const busy = toggling === `${selected.id}:${key}`
                      return (
                        <div key={key} className="flex items-center gap-3">
                          <span
                            className="min-w-0 flex-1 truncate text-xs text-zinc-400"
                            title={FEATURE_LABELS[key]}
                          >
                            {FEATURE_LABELS[key]}
                          </span>
                          <Toggle
                            checked={on}
                            disabled={busy}
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
