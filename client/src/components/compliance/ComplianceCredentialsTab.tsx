import { useState, useEffect, useCallback } from 'react'
import { Loader2, Award, BadgeCheck } from 'lucide-react'
import {
  fetchCompanyCertifications,
  fetchCompanyLicenses,
} from '../../api/compliance/compliance'
import type { CompanyCredential } from '../../api/compliance/compliance'

const SCOPE_LABELS: Record<string, string> = {
  federal: 'Federal',
  state: 'State',
  specialty: 'Specialty',
  county: 'County',
  city: 'City',
}

/**
 * Company-level certifications & licenses. These are populated by the admin
 * onboarding gap-analysis finalize step (company_certifications / company_licenses
 * → certifications_catalog / licenses_catalog). Not location-scoped — a credential
 * with a null location applies company-wide.
 */
export function ComplianceCredentialsTab({ companyId }: { companyId?: string }) {
  const [certs, setCerts] = useState<CompanyCredential[]>([])
  const [licenses, setLicenses] = useState<CompanyCredential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [c, l] = await Promise.all([
        fetchCompanyCertifications(companyId),
        fetchCompanyLicenses(companyId),
      ])
      setCerts(c)
      setLicenses(l)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load credentials')
    } finally {
      setLoading(false)
    }
  }, [companyId])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading credentials…
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CredentialSection
        title="Certifications"
        icon={<BadgeCheck className="w-4 h-4 text-emerald-400" />}
        items={certs}
        emptyHint="No company certifications yet. Completing an onboarding gap analysis populates these."
      />
      <CredentialSection
        title="Licenses"
        icon={<Award className="w-4 h-4 text-emerald-400" />}
        items={licenses}
        emptyHint="No company licenses yet. Completing an onboarding gap analysis populates these."
      />
    </div>
  )
}

function CredentialSection({
  title,
  icon,
  items,
  emptyHint,
}: {
  title: string
  icon: React.ReactNode
  items: CompanyCredential[]
  emptyHint: string
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
        <span className="text-[11px] text-zinc-500">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-zinc-600">{emptyHint}</p>
      ) : (
        <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
          {items.map((it) => (
            <li key={it.id} className="p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-zinc-100">{it.name}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    {it.issuing_authority || '—'} ·{' '}
                    {SCOPE_LABELS[it.scope_level] || it.scope_level}
                    {it.renewal_months ? ` · renews every ${it.renewal_months} mo` : ''}
                  </p>
                  {it.description && (
                    <p className="text-[11px] text-zinc-500 mt-1">{it.description}</p>
                  )}
                  {it.source_url && (
                    <a
                      href={it.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-emerald-300 hover:underline mt-1 inline-block"
                    >
                      Source ↗
                    </a>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-2">
                  {it.location_id === null && (
                    <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                      Company-wide
                    </span>
                  )}
                  <span className="text-[10px] rounded px-1.5 py-0.5 bg-emerald-500/10 text-emerald-300">
                    {it.status}
                  </span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
