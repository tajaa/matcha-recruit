import { useEffect, useState } from 'react'
import { ToggleLeft, Search, Loader2 } from 'lucide-react'
import { Card, Badge, Toggle, LABEL } from '../../components/ui'
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

type CompanyFeatures = {
  id: string
  company_name: string
  enabled_features: Record<string, boolean>
}

export default function Features() {
  const [companies, setCompanies] = useState<CompanyFeatures[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<CompanyFeatures[]>('/admin/company-features')
      .then(setCompanies)
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = companies.filter((c) =>
    c.company_name.toLowerCase().includes(search.toLowerCase())
  )

  async function toggle(companyId: string, feature: string, enabled: boolean) {
    const key = `${companyId}:${feature}`
    console.log('Toggle:', { companyId, feature, enabled })
    setToggling(key)
    setError(null)
    try {
      const res = await api.patch<{ enabled_features: Record<string, boolean> }>(
        `/admin/company-features/${companyId}`,
        { feature, enabled }
      )
      setCompanies((prev) =>
        prev.map((c) =>
          c.id === companyId
            ? { ...c, enabled_features: res.enabled_features }
            : c
        )
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Toggle failed')
    } finally {
      setToggling(null)
    }
  }

  const featureKeys = Object.keys(FEATURE_LABELS)
  const enabledCount = (features: Record<string, boolean>) =>
    featureKeys.filter((k) => features[k]).length

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-black">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <ToggleLeft className="h-4 w-4 text-emerald-400" /> Business Features
        </h1>
        <span className="hidden text-xs text-zinc-500 md:block">Toggle feature access per company.</span>
      </div>

      {/* Stat bar */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-white/[0.06] px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-zinc-500">
        <span>Companies <b className="text-zinc-100">{companies.length || '—'}</b></span>
        <span>Features <b className="text-zinc-100">{featureKeys.length}</b></span>
      </div>

      {/* Search */}
      <div className="border-b border-white/[0.06] px-4 py-3">
        <div className="relative max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search companies…"
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] pl-9 pr-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-white/[0.16]"
          />
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <p className="mb-4 rounded border border-red-900/30 bg-red-950/30 px-3 py-2 text-sm text-red-400">
            {error}
          </p>
        )}

        {loading ? (
          <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
        ) : filtered.length === 0 ? (
          <p className="text-sm text-zinc-500">No companies found.</p>
        ) : (
          <div className="space-y-4">
            {filtered.map((company) => (
              <Card key={company.id}>
                <div className="flex items-center justify-between mb-5">
                  <h3 className="text-sm font-semibold text-zinc-100">
                    {company.company_name}
                  </h3>
                  <Badge variant="neutral">
                    {enabledCount(company.enabled_features)}/{featureKeys.length} enabled
                  </Badge>
                </div>
                <div className="space-y-4">
                  {FEATURE_GROUPS.map((group) => (
                    <div key={group.label}>
                      <div className={`mb-2 ${LABEL}`}>{group.label}</div>
                      <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-5 gap-y-3">
                        {Object.keys(group.features).map((key) => {
                          const on = !!company.enabled_features[key]
                          const busy = toggling === `${company.id}:${key}`
                          return (
                            <div key={key} className="flex items-center gap-3">
                              <span className="min-w-0 flex-1 truncate text-sm text-zinc-400" title={FEATURE_LABELS[key]}>
                                {FEATURE_LABELS[key]}
                              </span>
                              <Toggle
                                checked={on}
                                disabled={busy}
                                onChange={(v) => toggle(company.id, key, v)}
                              />
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
