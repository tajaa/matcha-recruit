import { useEffect, useState } from 'react'
import { Check, Loader2, Plus, Trash2, Upload } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../../api/client'
import { scOnboardingApi } from '../../../api/sc-onboarding/scOnboarding'
import { useMe } from '../../../hooks/useMe'
import type {
  CompanySize,
  ScCertificateSetup,
  ScEmployeeImport,
  ScJobSetup,
  ScLocationImport,
  ScOnboardingSubmission,
} from '../../../types/scOnboarding'
import { Button, FileUpload, Input, Select, Toggle } from '../../ui'
import {
  EMPLOYEE_COLUMNS,
  LOCATION_COLUMNS,
  parseEmployeesCsv,
  parseLocationsCsv,
} from './csv'

const COMPANY_SIZES: { value: CompanySize; label: string }[] = [
  { value: '1-10', label: '1–10 employees' },
  { value: '11-50', label: '11–50 employees' },
  { value: '51-100', label: '51–100 employees' },
  { value: '101-250', label: '101–250 employees' },
  { value: '251-500', label: '251–500 employees' },
  { value: '501+', label: '501+ employees' },
]

const STEPS = ['Company', 'Locations', 'Employees', 'Jobs & certificates', 'Review']

function emptyCertificate(): ScCertificateSetup {
  return { name: '', is_required: true, schedule_blocking: true }
}

function emptyJob(): ScJobSetup {
  return { name: '', credential_grace_days: 7, certificates: [emptyCertificate()] }
}

function normalized(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function hasDuplicates(values: string[]) {
  const normalizedValues = values.map(normalized)
  return new Set(normalizedValues).size !== normalizedValues.length
}

function csvSummary(label: string, count: number, columns: readonly string[]) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-zinc-300">{count ? `${count} ${label} ready to import` : `No ${label} selected`}</p>
      <p className="break-all font-mono text-[11px] text-zinc-500">{columns.join(',')}</p>
    </div>
  )
}

export default function ScOnboardingWizard() {
  const navigate = useNavigate()
  const { refresh } = useMe()
  const [step, setStep] = useState(0)
  const [companyName, setCompanyName] = useState('')
  const [companySize, setCompanySize] = useState<CompanySize | ''>('')
  const [naicsCode, setNaicsCode] = useState('')
  const [industry, setIndustry] = useState('')
  const [locations, setLocations] = useState<ScLocationImport[]>([])
  const [employees, setEmployees] = useState<ScEmployeeImport[]>([])
  const [jobs, setJobs] = useState<ScJobSetup[]>([emptyJob()])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    scOnboardingApi.status()
      .then((status) => {
        if (cancelled) return
        if (status.completed) navigate('/app', { replace: true })
        else setCompanyName(status.company_name)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : 'Could not load account setup.')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [navigate])

  function companyError(): string | null {
    if (!companySize) return 'Choose a company size.'
    if (!/^\d{2,6}$/.test(naicsCode.trim())) return 'NAICS code must contain 2–6 digits.'
    if (!industry.trim()) return 'Enter an industry.'
    return null
  }

  function jobsError(): string | null {
    if (!jobs.length) return 'Add at least one job.'
    if (jobs.some((job) => !job.name.trim())) return 'Every job needs a name.'
    if (hasDuplicates(jobs.map((job) => job.name))) return 'Every job needs a unique name.'
    if (jobs.some((job) => !Number.isInteger(job.credential_grace_days) || job.credential_grace_days < 0 || job.credential_grace_days > 365)) {
      return 'Credential grace days must be a whole number from 0 to 365.'
    }
    if (jobs.some((job) => job.certificates.some((certificate) => !certificate.name.trim()))) {
      return 'Every certificate needs a name.'
    }
    if (jobs.some((job) => hasDuplicates(job.certificates.map((certificate) => certificate.name)))) {
      return 'Certificate names must be unique within each job.'
    }
    if (!jobs.some((job) => job.certificates.some((certificate) => certificate.is_required))) {
      return 'Configure at least one mandatory certificate.'
    }
    const jobNames = new Set(jobs.map((job) => normalized(job.name)))
    const unknownJobTitle = employees.find((employee) => !jobNames.has(normalized(employee.job_title)))?.job_title
    if (unknownJobTitle) return `Employee job title must match a configured job: ${unknownJobTitle}`
    return null
  }

  function advance() {
    const validation = step === 0 ? companyError() : step === 3 ? jobsError() : null
    if (validation) {
      setError(validation)
      return
    }
    setError(null)
    setStep((current) => Math.min(current + 1, STEPS.length - 1))
  }

  async function loadCsv<T>(file: File, parser: (text: string) => T[], apply: (rows: T[]) => void) {
    setError(null)
    try {
      if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('Choose a .csv file.')
      apply(parser(await file.text()))
    } catch (caught) {
      apply([])
      setError(caught instanceof Error ? caught.message : 'Could not read CSV.')
    }
  }

  function updateJob(index: number, update: Partial<ScJobSetup>) {
    setJobs((current) => current.map((job, i) => i === index ? { ...job, ...update } : job))
  }

  function updateCertificate(jobIndex: number, certificateIndex: number, update: Partial<ScCertificateSetup>) {
    setJobs((current) => current.map((job, i) => i !== jobIndex ? job : {
      ...job,
      certificates: job.certificates.map((certificate, j) => {
        if (j !== certificateIndex) return certificate
        const next = { ...certificate, ...update }
        if (!next.is_required) next.schedule_blocking = false
        return next
      }),
    }))
  }

  async function complete() {
    const companyValidation = companyError()
    const jobValidation = jobsError()
    if (companyValidation || jobValidation || !companySize) {
      setError(companyValidation ?? jobValidation ?? 'Review the required fields.')
      return
    }
    const submission: ScOnboardingSubmission = {
      company: { company_size: companySize, naics_code: naicsCode.trim(), industry: industry.trim() },
      locations,
      employees,
      jobs,
    }
    setSubmitting(true)
    setError(null)
    try {
      await scOnboardingApi.complete(submission)
      await refresh()
      navigate('/app', { replace: true })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Setup could not be completed. Nothing was imported; review the details and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center bg-zinc-950"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>
  }

  return (
    <div className="min-h-screen bg-zinc-950 px-4 py-10 text-zinc-100">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-emerald-400">Matcha S&amp;C</p>
          <h1 className="mt-2 text-2xl font-semibold">Set up {companyName || 'your company'}</h1>
          <p className="mt-1 text-sm text-zinc-400">Nothing is created until you approve the final review.</p>
        </div>

        <ol className="grid grid-cols-5 gap-2" aria-label="Setup progress">
          {STEPS.map((label, index) => (
            <li key={label} className={`border-t-2 pt-2 text-[11px] ${index <= step ? 'border-emerald-500 text-zinc-200' : 'border-zinc-800 text-zinc-600'}`}>
              {index < step && <Check className="mr-1 inline h-3 w-3" />}{label}
            </li>
          ))}
        </ol>

        <div className="rounded-xl border border-white/[0.08] bg-zinc-900/60 p-6">
          {step === 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-medium">Company details</h2>
              <Select label="Company size" required options={COMPANY_SIZES} value={companySize} onChange={(event) => setCompanySize(event.target.value as CompanySize)} placeholder="Choose a range" />
              <Input label="NAICS code" required inputMode="numeric" maxLength={6} value={naicsCode} onChange={(event) => setNaicsCode(event.target.value)} placeholder="e.g. 722511" />
              <Input label="Industry" required maxLength={100} value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder="e.g. Full-service restaurants" />
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div><h2 className="text-lg font-medium">Locations</h2><p className="text-sm text-zinc-400">Optional. Exact duplicate location rows are rejected across this file and your company.</p></div>
              <FileUpload accept=".csv,text/csv" maxSizeMB={5} onFiles={(files) => { if (files[0]) void loadCsv(files[0], parseLocationsCsv, setLocations) }}>
                <Upload className="mx-auto mb-2 h-5 w-5" /><p>Drop a locations CSV or browse</p>
              </FileUpload>
              {csvSummary('locations', locations.length, LOCATION_COLUMNS)}
              {locations.length > 0 && <Button variant="ghost" size="sm" onClick={() => setLocations([])}>Skip and clear locations</Button>}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div><h2 className="text-lg font-medium">Employees</h2><p className="text-sm text-zinc-400">Optional. Job titles must exactly match a job configured in the next step. No invitations are sent.</p></div>
              <FileUpload accept=".csv,text/csv" maxSizeMB={5} onFiles={(files) => { if (files[0]) void loadCsv(files[0], parseEmployeesCsv, setEmployees) }}>
                <Upload className="mx-auto mb-2 h-5 w-5" /><p>Drop an employees CSV or browse</p>
              </FileUpload>
              {csvSummary('employees', employees.length, EMPLOYEE_COLUMNS)}
              {employees.length > 0 && <Button variant="ghost" size="sm" onClick={() => setEmployees([])}>Skip and clear employees</Button>}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <div><h2 className="text-lg font-medium">Jobs and mandatory certificates</h2><p className="text-sm text-zinc-400">A schedule-blocking certificate prevents assignment after the job grace period until valid evidence is on file.</p></div>
              {jobs.map((job, jobIndex) => (
                <div key={jobIndex} className="space-y-3 rounded-lg border border-white/[0.08] bg-zinc-950/50 p-4">
                  <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto]">
                    <Input label="Job name" value={job.name} maxLength={150} onChange={(event) => updateJob(jobIndex, { name: event.target.value })} placeholder="e.g. Line cook" />
                    <Input label="Credential grace days" type="number" min={0} max={365} value={job.credential_grace_days} onChange={(event) => updateJob(jobIndex, { credential_grace_days: Number(event.target.value) })} />
                    <Button aria-label="Remove job" variant="ghost" size="sm" disabled={jobs.length === 1} onClick={() => setJobs((current) => current.filter((_, i) => i !== jobIndex))}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                  {job.certificates.map((certificate, certificateIndex) => (
                    <div key={certificateIndex} className="grid items-end gap-3 sm:grid-cols-[1fr_auto_auto_auto]">
                      <Input label="Certificate" value={certificate.name} maxLength={200} onChange={(event) => updateCertificate(jobIndex, certificateIndex, { name: event.target.value })} placeholder="e.g. Food Handler Card" />
                      <label className="flex h-10 items-center gap-2 text-xs text-zinc-300"><Toggle size="sm" checked={certificate.is_required} onChange={(checked) => updateCertificate(jobIndex, certificateIndex, { is_required: checked })} />Mandatory</label>
                      <label className="flex h-10 items-center gap-2 text-xs text-zinc-300"><Toggle size="sm" checked={certificate.schedule_blocking} disabled={!certificate.is_required} onChange={(checked) => updateCertificate(jobIndex, certificateIndex, { schedule_blocking: checked })} />Blocks schedule</label>
                      <Button aria-label="Remove certificate" variant="ghost" size="sm" disabled={job.certificates.length === 1} onClick={() => updateJob(jobIndex, { certificates: job.certificates.filter((_, i) => i !== certificateIndex) })}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  ))}
                  <Button variant="ghost" size="sm" onClick={() => updateJob(jobIndex, { certificates: [...job.certificates, emptyCertificate()] })}><Plus className="h-3.5 w-3.5" />Add certificate</Button>
                </div>
              ))}
              <Button variant="secondary" size="sm" onClick={() => setJobs((current) => [...current, emptyJob()])}><Plus className="h-3.5 w-3.5" />Add job</Button>
            </div>
          )}

          {step === 4 && companySize && (
            <div className="space-y-5">
              <div><h2 className="text-lg font-medium">Review setup</h2><p className="text-sm text-zinc-400">Submission is atomic: if any item fails validation, no company setup records are created.</p></div>
              <dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-zinc-500">Company size</dt><dd>{companySize}</dd></div><div><dt className="text-zinc-500">NAICS</dt><dd>{naicsCode}</dd></div><div><dt className="text-zinc-500">Industry</dt><dd>{industry}</dd></div></dl>
              <div className="grid gap-3 sm:grid-cols-2">
                <ReviewList title={`Locations (${locations.length})`} items={locations.map((location) => `${location.name} — ${location.address}, ${location.city}, ${location.state} ${location.zipcode}`)} empty="Skipped" />
                <ReviewList title={`Employees (${employees.length})`} items={employees.map((employee) => `${employee.first_name} ${employee.last_name} — ${employee.email}; ${employee.job_title}, ${employee.department}; ${employee.work_state}`)} empty="Skipped" />
              </div>
              <ReviewList title={`Jobs (${jobs.length})`} items={jobs.map((job) => {
                const certificates = job.certificates.map((certificate) => `${certificate.name} (${certificate.is_required ? 'mandatory' : 'optional'}, ${certificate.schedule_blocking ? 'blocks scheduling' : 'does not block scheduling'})`).join('; ')
                return `${job.name} — ${job.credential_grace_days} grace day${job.credential_grace_days === 1 ? '' : 's'}; ${certificates || 'no certificates'}`
              })} empty="None" />
            </div>
          )}

          {error && <p role="alert" className="mt-5 rounded border border-red-900/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>}
          <div className="mt-6 flex justify-between">
            <Button variant="ghost" disabled={step === 0 || submitting} onClick={() => { setError(null); setStep((current) => current - 1) }}>Back</Button>
            {step < STEPS.length - 1 ? <Button onClick={advance}>Continue</Button> : <Button disabled={submitting} onClick={() => void complete()}>{submitting && <Loader2 className="h-4 w-4 animate-spin" />}Complete setup</Button>}
          </div>
        </div>
      </div>
    </div>
  )
}

function ReviewList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div className="rounded-lg border border-white/[0.08] p-3"><h3 className="text-xs font-medium uppercase tracking-wide text-zinc-500">{title}</h3>{items.length ? <ul className="mt-2 space-y-1 text-sm text-zinc-200">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-zinc-500">{empty}</p>}</div>
}
