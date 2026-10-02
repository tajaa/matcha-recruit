import { useEffect, useState } from 'react'
import { Check, Download, Loader2, Plus, Trash2, Upload } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../../api/client'
import { scOnboardingApi } from '../../../api/sc/scOnboarding'
import { useMe } from '../../../hooks/useMe'
import type {
  CompanySize,
  ScCertificateSetup,
  ScEmployeeImport,
  ScJobSetup,
  ScLocationImport,
  ScOnboardingStatus,
  ScOnboardingSubmission,
} from '../../../types/scOnboarding'
import { inferLocationTimezone, TIMEZONE_OPTIONS } from '../../../utils/locationTimezone'
import { EMPTY_STORE, StoreFields, storeFormError, type StoreForm } from '../../employees/StoreFields'
import { Button, FileUpload, Input, Select, Toggle } from '../../ui'

const COMPANY_SIZES: { value: CompanySize; label: string }[] = [
  { value: '1-10', label: '1–10 employees' },
  { value: '11-50', label: '11–50 employees' },
  { value: '51-100', label: '51–100 employees' },
  { value: '101-250', label: '101–250 employees' },
  { value: '251-500', label: '251–500 employees' },
  { value: '501+', label: '501+ employees' },
]

const STEPS = ['Company', 'Locations', 'Employees', 'Jobs & certificates', 'Review']

// ~12s of cover for the Stripe webhook that activates a paid S&C product.
const ACTIVATION_POLL_ATTEMPTS = 8
const ACTIVATION_POLL_MS = 1500

const EMPTY_CSV_COLUMNS = { locations: [], employees: [] }

// Starter files. Reserved example.com addresses only — a template row gets
// uploaded verbatim by someone trying it out.
const LOCATIONS_TEMPLATE =
  'name,address,city,state,zipcode\nDowntown,120 Main St,Oakland,CA,94607\nMission,455 Valencia St,San Francisco,CA,94103\n'
const EMPLOYEES_TEMPLATE =
  'email,first_name,last_name,work_state,job_title,department,location\n'
  + 'sam.rivera@example.com,Sam,Rivera,CA,Barista,Front of house,Downtown\n'
  + 'priya.shah@example.com,Priya,Shah,CA,Shift Lead,Front of house,Mission\n'

function downloadCsv(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function emptyCertificate(): ScCertificateSetup {
  return { name: '', is_required: true, schedule_blocking: true }
}

// Certificates are optional, so a new job starts with none: naming the job is
// enough to move on.
function emptyJob(): ScJobSetup {
  return { name: '', credential_grace_days: 7, certificates: [] }
}

/** A store's time zone is what lets its schedule publish. Pre-fill it where
 *  the state leaves no doubt; a split-zone state stays blank for the manager. */
function withTimezone(location: ScLocationImport): ScLocationImport {
  return { ...location, timezone: location.timezone || inferLocationTimezone(location.state) || '' }
}

// Shared verbatim with services/sc_onboarding.UNMATCHED_JOB_TITLES_MESSAGE.
const UNMATCHED_JOB_TITLES_MESSAGE =
  'Every employee job title needs a job. Add a job with the same name, or correct the title in the employee CSV and upload it again. Missing: '

function normalized(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

/** Distinct employee job titles with no job yet, in roster order. */
function unmatchedTitles(jobs: ScJobSetup[], employees: ScEmployeeImport[]): string[] {
  const seen = new Set(jobs.map((job) => normalized(job.name)))
  const titles: string[] = []
  for (const employee of employees) {
    const key = normalized(employee.job_title)
    if (seen.has(key)) continue
    seen.add(key)
    titles.push(employee.job_title.trim())
  }
  return titles
}

/** Adds a certificate-less job for every roster title that has none yet.
 *  The title is what assigns an imported employee to a job, so the manager
 *  should see every one of them instead of discovering them one error at a
 *  time. Blank rows go — they could only fail "Every job needs a name". */
function withRosterJobs(jobs: ScJobSetup[], employees: ScEmployeeImport[]): ScJobSetup[] {
  const titles = unmatchedTitles(jobs, employees)
  if (!titles.length) return jobs
  const kept = jobs.filter((job) => job.name.trim() || job.certificates.some((certificate) => certificate.name.trim()))
  return [...kept, ...titles.map((name) => ({ name, credential_grace_days: 7, certificates: [] }))]
}

function hasDuplicates(values: string[]) {
  const normalizedValues = values.map(normalized)
  return new Set(normalizedValues).size !== normalizedValues.length
}

function csvSummary(
  label: string,
  count: number,
  columns: readonly string[],
  busy: boolean,
  optional: readonly string[] = [],
) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-zinc-300">
        {busy
          ? `Checking ${label}…`
          : count ? `${count} ${label} ready to import` : `No ${label} selected`}
      </p>
      <p className="break-all font-mono text-[11px] text-zinc-500">{columns.join(',')}</p>
      {optional.length > 0 && (
        <p className="break-all font-mono text-[11px] text-zinc-600">optional: {optional.join(',')}</p>
      )}
    </div>
  )
}

/** Employees whose store name matches none of the stores entered. */
function unknownStores(locations: ScLocationImport[], employees: ScEmployeeImport[]): string[] {
  const known = new Set(locations.map((location) => normalized(location.name)))
  const missing = new Map<string, string>()
  for (const employee of employees) {
    const name = employee.location?.trim()
    if (name && !known.has(normalized(name)) && !missing.has(normalized(name))) missing.set(normalized(name), name)
  }
  return [...missing.values()]
}

/** How many employees will finish setup with no store, and so on no schedule. */
function unassignedCount(locations: ScLocationImport[], employees: ScEmployeeImport[]): number {
  if (locations.length === 1) return 0
  return employees.filter((employee) => !employee.location?.trim()).length
}

export default function ScOnboardingWizard() {
  const navigate = useNavigate()
  const { refresh } = useMe()
  const [step, setStep] = useState(0)
  const [companyName, setCompanyName] = useState('')
  const [companySize, setCompanySize] = useState<CompanySize | ''>('')
  const [naicsCode, setNaicsCode] = useState('')
  const [locations, setLocations] = useState<ScLocationImport[]>([])
  const [employees, setEmployees] = useState<ScEmployeeImport[]>([])
  const [jobs, setJobs] = useState<ScJobSetup[]>([emptyJob()])
  const [csvColumns, setCsvColumns] = useState<NonNullable<ScOnboardingStatus['csv_columns']>>(EMPTY_CSV_COLUMNS)
  const [optionalColumns, setOptionalColumns] = useState<NonNullable<ScOnboardingStatus['csv_optional_columns']>>(EMPTY_CSV_COLUMNS)
  const [storeForm, setStoreForm] = useState<StoreForm | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)
  const [parsing, setParsing] = useState<'locations' | 'employees' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    // Stripe returns the browser here as soon as checkout succeeds, which can
    // beat the checkout.session.completed webhook that flips the product's
    // gate flag. A 403 inside that window means "not activated yet", not a
    // dead end, so poll a bounded number of times before giving up.
    async function load(attempt: number) {
      try {
        const status = await scOnboardingApi.status()
        if (cancelled) return
        if (status.completed) {
          // The route guard reads the module-level /auth/me cache; navigating
          // without refreshing it first bounces the user straight back here.
          await refresh()
          if (!cancelled) navigate('/app', { replace: true })
          return
        }
        setCompanyName(status.company_name)
        setCsvColumns(status.csv_columns ?? EMPTY_CSV_COLUMNS)
        setOptionalColumns(status.csv_optional_columns ?? EMPTY_CSV_COLUMNS)
        // Signup already asked for headcount and industry — start from those.
        if (status.suggested_company_size) setCompanySize(status.suggested_company_size)
        if (status.suggested_naics_code) setNaicsCode(status.suggested_naics_code)
        setActivating(false)
        setLoading(false)
      } catch (caught: unknown) {
        if (cancelled) return
        if (caught instanceof ApiError && caught.status === 401) {
          // Not signed in: the setup link was opened cold. Nothing to show here.
          navigate('/login', { replace: true })
          return
        }
        if (caught instanceof ApiError && caught.status === 403 && attempt < ACTIVATION_POLL_ATTEMPTS) {
          setActivating(true)
          timer = setTimeout(() => { void load(attempt + 1) }, ACTIVATION_POLL_MS)
          return
        }
        setActivating(false)
        // The form would only collect answers the server then refuses, so the
        // reason is shown on its own instead of above a wizard that cannot save.
        setBlocked(caught instanceof ApiError ? caught.message : 'Could not load account setup.')
        setLoading(false)
      }
    }

    void load(0)
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [navigate, refresh])

  function companyError(): string | null {
    if (!companySize) return 'Choose a company size.'
    if (!/^\d{2,6}$/.test(naicsCode.trim())) return 'NAICS code must contain 2–6 digits.'
    return null
  }

  // Mirrors services/sc_onboarding.resolve_location_timezone: a store with no
  // time zone cannot publish a schedule, so setup does not create one.
  function locationsError(): string | null {
    const missing = locations.find((location) => !location.timezone)
    return missing ? `Choose a time zone for ${missing.name}.` : null
  }

  // Mirrors services/sc_onboarding.employee_store_keys.
  function employeesError(): string | null {
    const unknown = unknownStores(locations, employees)
    if (!unknown.length) return null
    return `Every employee location must match a location name from the locations step. Not found: ${unknown.join(', ')}`
  }

  // Mirrors the server contract (models/sc_onboarding.py +
  // services/sc_onboarding.validate_sc_submission): unique names, and every
  // employee job title matching a job on this step. Certificates are optional
  // — a job, or the whole setup, may have none. Change both together.
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
    const missing = unmatchedTitles(jobs, employees)
    if (missing.length) {
      return UNMATCHED_JOB_TITLES_MESSAGE + [...missing].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })).join(', ')
    }
    return null
  }

  function advance() {
    const validation = [companyError, locationsError, employeesError, jobsError][step]?.() ?? null
    if (validation) {
      setError(validation)
      return
    }
    setError(null)
    if (step === 2) setJobs((current) => withRosterJobs(current, employees))
    setStep((current) => Math.min(current + 1, STEPS.length - 1))
  }

  async function loadCsv<T>(
    kind: 'locations' | 'employees',
    file: File,
    parser: (file: File) => Promise<T[]>,
    apply: (rows: T[]) => void,
  ) {
    setError(null)
    setParsing(kind)
    try {
      if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('Choose a .csv file.')
      apply(await parser(file))
    } catch (caught) {
      apply([])
      setError(caught instanceof Error ? caught.message : 'Could not read CSV.')
    } finally {
      setParsing(null)
    }
  }

  function addStore() {
    if (!storeForm) return
    const problem = storeFormError(storeForm)
    if (problem) { setError(problem); return }
    const store: ScLocationImport = {
      name: storeForm.name.trim(),
      address: storeForm.address.trim(),
      city: storeForm.city.trim(),
      state: storeForm.state,
      zipcode: storeForm.zipcode.trim(),
      timezone: storeForm.timezone,
    }
    if (locations.some((location) => normalized(location.name) === normalized(store.name))) {
      setError(`You already have a location named ${store.name}.`)
      return
    }
    setError(null)
    setLocations((current) => [...current, store])
    setStoreForm(null)
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
    const validation = companyError() ?? locationsError() ?? employeesError() ?? jobsError()
    if (validation || !companySize) {
      setError(validation ?? 'Review the required fields.')
      return
    }
    const submission: ScOnboardingSubmission = {
      company: { company_size: companySize, naics_code: naicsCode.trim() },
      locations,
      employees,
      jobs,
    }
    setSubmitting(true)
    setError(null)
    try {
      await scOnboardingApi.complete(submission)
      await refresh()
      // Straight to the schedule: it is what they signed up for, and every
      // store and employee they just entered is already on it.
      navigate('/ops/schedule', { replace: true })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Setup could not be completed. Nothing was imported; review the details and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-zinc-950">
        <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
        {activating && <p className="text-sm text-zinc-400">Finishing activation…</p>}
      </div>
    )
  }

  if (blocked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-zinc-100">
        <div className="max-w-md space-y-4 rounded-xl border border-white/[0.08] bg-zinc-900/60 p-6">
          <h1 className="text-lg font-semibold">Setup isn't ready yet</h1>
          <p role="alert" className="text-sm text-zinc-300">{blocked}</p>
          <p className="text-sm text-zinc-500">
            If you just paid, activation can take a minute. Nothing you entered is lost — there is nothing to enter yet.
          </p>
          <Button onClick={() => window.location.reload()}>Try again</Button>
        </div>
      </div>
    )
  }

  const unassigned = unassignedCount(locations, employees)

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
              <p className="text-sm text-zinc-400">Filled in from what you told us at signup where we could. Change anything that's off.</p>
              <Select label="Company size" required options={COMPANY_SIZES} value={companySize} onChange={(event) => setCompanySize(event.target.value as CompanySize)} placeholder="Choose a range" />
              <Input label="NAICS code" required inputMode="numeric" maxLength={6} value={naicsCode} onChange={(event) => setNaicsCode(event.target.value)} placeholder="e.g. 722511" />
              {/* Industry is deliberately not re-asked: signup already stored it
                  from the shared INDUSTRY_OPTIONS vocabulary, and free text here
                  would overwrite that controlled value. */}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-medium">Locations</h2>
                <p className="text-sm text-zinc-400">Each store you add here gets its own schedule. Add one below, or upload a file if you have several. You can add more later from the schedule.</p>
              </div>
              {locations.length > 0 && (
                <ul className="space-y-2">
                  {locations.map((location, index) => (
                    <li key={`${location.name}-${index}`} className="grid items-end gap-3 rounded-lg border border-white/[0.08] bg-zinc-950/50 p-3 sm:grid-cols-[1fr_260px_auto]">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-zinc-100">{location.name}</p>
                        <p className="truncate text-xs text-zinc-500">{location.address}, {location.city}, {location.state} {location.zipcode}</p>
                      </div>
                      <Select
                        label={`Time zone for ${location.name}`}
                        options={TIMEZONE_OPTIONS}
                        value={location.timezone ?? ''}
                        onChange={(event) => setLocations((current) => current.map((item, i) => i === index ? { ...item, timezone: event.target.value } : item))}
                        placeholder="Select a time zone"
                      />
                      <Button aria-label={`Remove ${location.name}`} variant="ghost" size="sm" onClick={() => setLocations((current) => current.filter((_, i) => i !== index))}><Trash2 className="h-4 w-4" /></Button>
                    </li>
                  ))}
                </ul>
              )}
              {storeForm ? (
                <div className="space-y-3 rounded-lg border border-white/[0.08] bg-zinc-950/50 p-4">
                  <StoreFields value={storeForm} onChange={setStoreForm} />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={addStore}>Add this store</Button>
                    <Button variant="ghost" size="sm" onClick={() => { setStoreForm(null); setError(null) }}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <Button variant="secondary" size="sm" onClick={() => setStoreForm(EMPTY_STORE)}><Plus className="h-3.5 w-3.5" />Add a store</Button>
              )}
              <FileUpload accept=".csv,text/csv" maxSizeMB={5} onFiles={(files) => { if (files[0]) void loadCsv('locations', files[0], scOnboardingApi.parseLocationsCsv, (rows) => setLocations(rows.map(withTimezone))) }}>
                <Upload className="mx-auto mb-2 h-5 w-5" /><p>Drop a locations CSV or browse</p>
              </FileUpload>
              {csvSummary('locations', locations.length, csvColumns.locations, parsing === 'locations')}
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={() => downloadCsv('locations-template.csv', LOCATIONS_TEMPLATE)}><Download className="h-3.5 w-3.5" />Download a template</Button>
                {locations.length > 0 && <Button variant="ghost" size="sm" onClick={() => setLocations([])}>Skip and clear locations</Button>}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div><h2 className="text-lg font-medium">Employees</h2><p className="text-sm text-zinc-400">Optional. Each job title in the file becomes a job in the next step. No invitations are sent.</p></div>
              <FileUpload accept=".csv,text/csv" maxSizeMB={5} onFiles={(files) => { if (files[0]) void loadCsv('employees', files[0], scOnboardingApi.parseEmployeesCsv, setEmployees) }}>
                <Upload className="mx-auto mb-2 h-5 w-5" /><p>Drop an employees CSV or browse</p>
              </FileUpload>
              {csvSummary('employees', employees.length, csvColumns.employees, parsing === 'employees', optionalColumns.employees)}
              {employees.length > 0 && locations.length === 1 && (
                <p className="text-sm text-zinc-300">Everyone will be scheduled at {locations[0].name}.</p>
              )}
              {employees.length > 0 && unassigned > 0 && (
                <p className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
                  {unassigned} {unassigned === 1 ? 'employee has' : 'employees have'} no store, so they won't appear on a schedule yet.
                  {locations.length > 1
                    ? ' Add a location column with the store name and upload again, or assign them from the schedule after setup.'
                    : ' Add a store in the previous step, or assign them from the schedule after setup.'}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={() => downloadCsv('employees-template.csv', EMPLOYEES_TEMPLATE)}><Download className="h-3.5 w-3.5" />Download a template</Button>
                {employees.length > 0 && <Button variant="ghost" size="sm" onClick={() => setEmployees([])}>Skip and clear employees</Button>}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <div><h2 className="text-lg font-medium">Jobs and certificates</h2><p className="text-sm text-zinc-400">Name the roles you schedule. Certificates are optional: add one only where a role needs it. A schedule-blocking certificate prevents assignment after the job grace period until valid evidence is on file.{employees.length > 0 && ' Every job title from your employee file is listed here; a job can have no certificate.'}</p></div>
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
                      <Button aria-label="Remove certificate" variant="ghost" size="sm" onClick={() => updateJob(jobIndex, { certificates: job.certificates.filter((_, i) => i !== certificateIndex) })}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  ))}
                  {job.certificates.length === 0 && <p className="text-xs text-zinc-500">No certificate required for this job.</p>}
                  <Button variant="ghost" size="sm" onClick={() => updateJob(jobIndex, { certificates: [...job.certificates, emptyCertificate()] })}><Plus className="h-3.5 w-3.5" />Add certificate</Button>
                </div>
              ))}
              <Button variant="secondary" size="sm" onClick={() => setJobs((current) => [...current, emptyJob()])}><Plus className="h-3.5 w-3.5" />Add job</Button>
            </div>
          )}

          {step === 4 && companySize && (
            <div className="space-y-5">
              <div><h2 className="text-lg font-medium">Review setup</h2><p className="text-sm text-zinc-400">Submission is atomic: if any item fails validation, no company setup records are created.</p></div>
              <dl className="grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-zinc-500">Company size</dt><dd>{companySize}</dd></div><div><dt className="text-zinc-500">NAICS</dt><dd>{naicsCode}</dd></div></dl>
              <div className="grid gap-3 sm:grid-cols-2">
                <ReviewList title={`Locations (${locations.length})`} items={locations.map((location) => `${location.name} — ${location.address}, ${location.city}, ${location.state} ${location.zipcode}; ${location.timezone}`)} empty="Skipped" />
                <ReviewList title={`Employees (${employees.length})`} items={employees.map((employee) => {
                  const store = employee.location?.trim() || (locations.length === 1 ? locations[0].name : 'no store yet')
                  return `${employee.first_name} ${employee.last_name} — ${employee.email}; ${employee.job_title}, ${employee.department}; ${store}`
                })} empty="Skipped" />
              </div>
              {unassigned > 0 && (
                <p className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
                  {unassigned} {unassigned === 1 ? 'employee has' : 'employees have'} no store yet. You can finish setup and assign them from the schedule.
                </p>
              )}
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
