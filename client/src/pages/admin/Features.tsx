import { useEffect, useState } from 'react'
import { Card, Badge, Toggle, Input } from '../../components/ui'
import { api } from '../../api/client'

const FEATURE_LABELS: Record<string, string> = {
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
  matcha_work: 'Matcha Work',
  risk_assessment: 'Risk Assessment',
  training: 'Training',
  i9: 'I-9 Verification',
  cobra: 'COBRA',
  separation_agreements: 'Separation Agreements',
  vibe_checks: 'Vibe Checks',
  enps: 'eNPS',
  performance_reviews: 'Performance Reviews',
}

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
    setToggling(key)
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
    } finally {
      setToggling(null)
    }
  }

  const featureKeys = Object.keys(FEATURE_LABELS)
  const enabledCount = (features: Record<string, boolean>) =>
    featureKeys.filter((k) => features[k]).length

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">
        Business Features
      </h1>
      <p className="mt-2 text-sm text-zinc-500">
        Toggle feature access per company.
      </p>

      <div className="mt-6 max-w-xs">
        <Input
          label=""
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <p className="mt-6 text-sm text-zinc-500">Loading...</p>
      ) : filtered.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-500">No companies found.</p>
      ) : (
        <div className="mt-6 space-y-4">
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
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
                {featureKeys.map((key) => {
                  const on = !!company.enabled_features[key]
                  const busy = toggling === `${company.id}:${key}`
                  return (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">
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
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
