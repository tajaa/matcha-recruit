import { useState, useEffect, useCallback } from 'react'
import { Loader2, Award, BadgeCheck, FileWarning } from 'lucide-react'
import {
  fetchCompanyCertifications,
  fetchCompanyLicenses,
  fetchEmployeeDocumentExpiries,
} from '../../api/compliance'
import type {
  CompanyCredential,
  EmployeeDocumentExpiry,
  EmployeeDocumentExpiryStatus,
} from '../../api/compliance'
import { formatDateOnly } from '../../utils/dateFormat'

const SCOPE_LABELS: Record<string, string> = {
  federal: 'Federal',
  state: 'State',
  specialty: 'Specialty',
  county: 'County',
  city: 'City',
}

/**
 * Employee document expiries plus the company-level certifications and licenses
 * populated by onboarding. Compliance Lite uses employeeOnly because the company
 * catalog endpoints remain part of full Compliance.
 */
export function ComplianceCredentialsTab({
  companyId,
  employeeOnly = false,
}: {
  companyId?: string
  employeeOnly?: boolean
}) {
  const [certs, setCerts] = useState<CompanyCredential[]>([])
  const [licenses, setLicenses] = useState<CompanyCredential[]>([])
  const [employees, setEmployees] = useState<EmployeeDocumentExpiry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (employeeOnly) {
        setEmployees(await fetchEmployeeDocumentExpiries(companyId))
      } else {
        const [c, l, employeeExpiries] = await Promise.all([
          fetchCompanyCertifications(companyId),
          fetchCompanyLicenses(companyId),
          fetchEmployeeDocumentExpiries(companyId),
        ])
        setCerts(c)
        setLicenses(l)
        setEmployees(employeeExpiries)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load credentials')
    } finally {
      setLoading(false)
    }
  }, [companyId, employeeOnly])

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
      <EmployeeExpirySection employees={employees} />
      {!employeeOnly && (
        <>
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
        </>
      )}
    </div>
  )
}

const STATUS_PRESENTATION: Record<
  EmployeeDocumentExpiry['status'],
  { label: string; badge: string; border: string }
> = {
  expired: {
    label: 'Expired — action required',
    badge: 'border-red-500/40 bg-red-500/10 text-red-300',
    border: 'border-red-500/30',
  },
  expiring_soon: {
    label: 'Expiring soon',
    badge: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
    border: 'border-amber-500/30',
  },
  unknown: {
    label: 'Expiry unknown',
    badge: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
    border: 'border-sky-500/30',
  },
  no_actionable_expiry: {
    label: 'No actionable expiry',
    badge: 'border-zinc-700 bg-zinc-800/60 text-zinc-400',
    border: 'border-zinc-800',
  },
}

const DOCUMENT_STATUS_LABEL: Record<EmployeeDocumentExpiryStatus, string> = {
  expired: 'Expired',
  expiring_soon: 'Expiring soon',
  unknown: 'Expiry unknown',
  current: 'Current',
}

function EmployeeExpirySection({ employees }: { employees: EmployeeDocumentExpiry[] }) {
  const flagged = employees.filter((employee) => employee.status !== 'no_actionable_expiry').length

  return (
    <section>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <FileWarning className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-medium text-zinc-200">Employee document expiries</h3>
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            Credentials warn 30 days before expiry; work permits warn 14 days before expiry.
          </p>
        </div>
        <span className="shrink-0 text-[11px] text-zinc-500">
          {flagged} need{flagged === 1 ? 's' : ''} attention
        </span>
      </div>

      {employees.length === 0 ? (
        <p className="text-xs text-zinc-600">No active employees to review.</p>
      ) : (
        <ul className="space-y-2">
          {employees.map((employee) => {
            const presentation = STATUS_PRESENTATION[employee.status]
            return (
              <li
                key={employee.employee_id}
                className={`rounded-lg border bg-zinc-900/40 p-3 ${presentation.border}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-zinc-100">{employee.employee_name}</p>
                  <span
                    className={`rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${presentation.badge}`}
                  >
                    {presentation.label}
                  </span>
                </div>
                {employee.documents.length === 0 ? (
                  <p className="mt-2 text-xs text-zinc-500">No expiring credential or work-permit records.</p>
                ) : (
                  <ul className="mt-2 divide-y divide-zinc-800/80 border-t border-zinc-800/80">
                    {employee.documents.map((document) => (
                      <li
                        key={`${document.kind}:${document.id}`}
                        className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 text-xs"
                      >
                        <span className="text-zinc-300">
                          {document.document_type}
                          {document.location_name ? ` · ${document.location_name}` : ''}
                        </span>
                        <span className="text-right text-zinc-500">
                          <span className="font-medium text-zinc-300">
                            {DOCUMENT_STATUS_LABEL[document.expiry_status]}
                          </span>
                          {' · '}
                          {document.expiry_date
                            ? `Expires ${formatDateOnly(document.expiry_date)}`
                            : 'Expiry date unknown'}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
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
