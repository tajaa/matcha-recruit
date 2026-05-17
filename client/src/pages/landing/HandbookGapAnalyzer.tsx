import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Loader2, ShieldAlert, FileSearch, MapPin, UploadCloud, Lock } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { useMe } from '../../hooks/useMe'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const BASE = import.meta.env.VITE_API_URL ?? '/api'
const MAX_PDF_BYTES = 10 * 1024 * 1024
const SIGNUP_HREF = '/auth/resources-signup?next=%2Fhandbook-gap-analyzer'
const LOGIN_HREF = '/login?next=%2Fhandbook-gap-analyzer'
const EMBEDDED_PATH = '/app/resources/handbook-audit'

const STATES: { code: string; name: string }[] = [
  { code: 'AL', name: 'Alabama' }, { code: 'AK', name: 'Alaska' }, { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' }, { code: 'CA', name: 'California' }, { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' }, { code: 'DE', name: 'Delaware' }, { code: 'DC', name: 'D.C.' },
  { code: 'FL', name: 'Florida' }, { code: 'GA', name: 'Georgia' }, { code: 'HI', name: 'Hawaii' },
  { code: 'ID', name: 'Idaho' }, { code: 'IL', name: 'Illinois' }, { code: 'IN', name: 'Indiana' },
  { code: 'IA', name: 'Iowa' }, { code: 'KS', name: 'Kansas' }, { code: 'KY', name: 'Kentucky' },
  { code: 'LA', name: 'Louisiana' }, { code: 'ME', name: 'Maine' }, { code: 'MD', name: 'Maryland' },
  { code: 'MA', name: 'Massachusetts' }, { code: 'MI', name: 'Michigan' }, { code: 'MN', name: 'Minnesota' },
  { code: 'MS', name: 'Mississippi' }, { code: 'MO', name: 'Missouri' }, { code: 'MT', name: 'Montana' },
  { code: 'NE', name: 'Nebraska' }, { code: 'NV', name: 'Nevada' }, { code: 'NH', name: 'New Hampshire' },
  { code: 'NJ', name: 'New Jersey' }, { code: 'NM', name: 'New Mexico' }, { code: 'NY', name: 'New York' },
  { code: 'NC', name: 'North Carolina' }, { code: 'ND', name: 'North Dakota' }, { code: 'OH', name: 'Ohio' },
  { code: 'OK', name: 'Oklahoma' }, { code: 'OR', name: 'Oregon' }, { code: 'PA', name: 'Pennsylvania' },
  { code: 'RI', name: 'Rhode Island' }, { code: 'SC', name: 'South Carolina' }, { code: 'SD', name: 'South Dakota' },
  { code: 'TN', name: 'Tennessee' }, { code: 'TX', name: 'Texas' }, { code: 'UT', name: 'Utah' },
  { code: 'VT', name: 'Vermont' }, { code: 'VA', name: 'Virginia' }, { code: 'WA', name: 'Washington' },
  { code: 'WV', name: 'West Virginia' }, { code: 'WI', name: 'Wisconsin' }, { code: 'WY', name: 'Wyoming' },
]

const INDUSTRIES = [
  { value: 'general', label: 'General / Cross-industry' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'hospitality', label: 'Hospitality / Restaurants' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'retail', label: 'Retail' },
  { value: 'professional_services', label: 'Professional Services' },
  { value: 'tech', label: 'Tech / Software' },
]

interface HandbookGapAnalyzerProps {
  embedded?: boolean
}

export default function HandbookGapAnalyzer({ embedded = false }: HandbookGapAnalyzerProps) {
  const { me, loading } = useMe()

  if (!embedded && !loading && me) {
    return <Navigate to={EMBEDDED_PATH} replace />
  }

  if (embedded) {
    return (
      <div className="max-w-[1100px] mx-auto px-6 sm:px-10 py-10">
        <EmbeddedHero />
        <div className="grid lg:grid-cols-3 gap-6 mb-10">
          <Pillar icon={UploadCloud} title="Upload" body="Drop in your current handbook PDF. Up to 10MB, kept private." />
          <Pillar icon={MapPin} title="Scope" body="Pick one state. Run again for additional locations." />
          <Pillar icon={FileSearch} title="Diagnose" body="Get a per-clause gap list. Severity, citation, what good looks like." />
        </div>
        {loading ? (
          <div className="text-center py-12" style={{ color: MUTED }}>
            <Loader2 className="w-5 h-5 animate-spin inline" />
          </div>
        ) : (
          <UploaderForm embedded />
        )}
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <MarketingNav />

      <main className="max-w-[1100px] mx-auto px-6 sm:px-10 pt-28 pb-24">
        <Hero authed={!!me} />

        <div className="grid lg:grid-cols-3 gap-6 mb-12">
          <Pillar icon={UploadCloud} title="Upload" body="Drop in your current handbook PDF. Up to 10MB, kept private." />
          <Pillar icon={MapPin} title="Scope" body="Pick one state. Run again for additional locations." />
          <Pillar icon={FileSearch} title="Diagnose" body="Get a per-clause gap list. Severity, citation, what good looks like." />
        </div>

        {loading ? (
          <div className="text-center py-12" style={{ color: MUTED }}>
            <Loader2 className="w-5 h-5 animate-spin inline" />
          </div>
        ) : (
          <SignupGate />
        )}
      </main>

      <MarketingFooter />
    </div>
  )
}

function EmbeddedHero() {
  return (
    <header className="mb-10">
      <h1
        className="tracking-tight mb-3"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: 'clamp(1.6rem, 3vw, 2.4rem)', color: INK }}
      >
        Handbook Audit
      </h1>
      <p className="text-[15px] leading-relaxed max-w-[680px]" style={{ color: MUTED }}>
        Upload your handbook PDF and pick a state. We grade each section against
        that state's required policies and return a clause-by-clause gap list.
      </p>
    </header>
  )
}

function Hero({ authed }: { authed: boolean }) {
  return (
    <header className="text-center mb-12">
      <p
        className="text-[11px] uppercase tracking-[0.3em] mb-4"
        style={{ color: MUTED, fontFamily: 'var(--font-mono)' }}
      >
        FREE TOOL · NO CREDIT CARD
      </p>
      <h1
        className="tracking-tight mb-5"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: 'clamp(2rem, 4.2vw, 3.4rem)', color: INK }}
      >
        See what's missing from your employee handbook in 90 seconds.
      </h1>
      <p
        className="max-w-[680px] mx-auto text-[16px] leading-relaxed"
        style={{ color: MUTED }}
      >
        {authed
          ? 'Upload your handbook, pick a state, get a gap report a lawyer would charge $2k–$5k for.'
          : 'Compare your handbook against the actual jurisdiction-by-jurisdiction policy requirements your team is on the hook for. A free Matcha account unlocks the audit.'}
      </p>
    </header>
  )
}

function SignupGate() {
  return (
    <div
      className="rounded-2xl p-9 text-center"
      style={{ backgroundColor: INK, color: BG }}
    >
      <Lock className="w-7 h-7 mx-auto mb-4" />
      <h2
        className="tracking-tight mb-3"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.75rem' }}
      >
        Create a free account to run the audit.
      </h2>
      <p className="text-sm max-w-lg mx-auto mb-6" style={{ color: 'rgba(245,242,237,0.75)' }}>
        Free tier — no card, no trial. The account also unlocks 14 HR templates,
        the compliance audit, calculators, and the job descriptions library.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          to={SIGNUP_HREF}
          className="inline-flex items-center px-6 h-11 rounded-full text-sm font-medium"
          style={{ backgroundColor: BG, color: INK }}
        >
          Create free account
        </Link>
        <Link
          to={LOGIN_HREF}
          className="inline-flex items-center px-6 h-11 rounded-full text-sm font-medium"
          style={{ border: `1px solid rgba(245,242,237,0.3)`, color: BG }}
        >
          I already have one
        </Link>
      </div>
      <p className="mt-5 text-[11px]" style={{ color: 'rgba(245,242,237,0.55)' }}>
        Gating is in place to prevent abuse — every audit ties back to a real account.
      </p>
    </div>
  )
}

interface QuotaState {
  used: number
  limit: number
  remaining: number
  resets_at: string
}

function UploaderForm({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [industry, setIndustry] = useState('general')
  const [selectedState, setSelectedState] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [quota, setQuota] = useState<QuotaState | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    const token = localStorage.getItem('matcha_access_token')
    fetch(`${BASE}/resources/handbook-gap-analyzer/quota`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d) setQuota(d) })
      .catch(() => { /* non-fatal */ })
    return () => { cancelled = true }
  }, [])

  const quotaExhausted = quota ? quota.remaining <= 0 : false

  function handleFile(file: File | null) {
    setError(null)
    if (!file) {
      setPdfFile(null)
      return
    }
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setError('Upload must be a PDF.')
      return
    }
    if (file.size > MAX_PDF_BYTES) {
      setError('PDF must be 10MB or smaller.')
      return
    }
    setPdfFile(file)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!pdfFile) {
      setError('Pick the PDF first.')
      return
    }
    if (!selectedState) {
      setError('Pick a state.')
      return
    }

    setSubmitting(true)
    try {
      const fd = new FormData()
      fd.append('pdf', pdfFile)
      fd.append('states', selectedState)
      fd.append('industry', industry)
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/resources/handbook-gap-analyzer/analyze`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.detail || 'Could not start the analysis. Try again.')
        setSubmitting(false)
        return
      }
      const resultPath = embedded
        ? `${EMBEDDED_PATH}/result/${data.report_id}`
        : `/handbook-gap-analyzer/result/${data.report_id}`
      navigate(resultPath)
    } catch {
      setError('Network error. Try again.')
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl p-7 md:p-9"
      style={{ backgroundColor: 'rgba(255,255,255,0.55)', border: `1px solid ${LINE}` }}
    >
      {quota && (
        <div
          className="mb-6 flex items-center justify-between rounded-lg px-4 py-2.5 text-[12px]"
          style={{
            backgroundColor: quotaExhausted ? 'rgba(206,145,120,0.1)' : 'rgba(31,29,26,0.04)',
            border: `1px solid ${quotaExhausted ? 'rgba(206,145,120,0.3)' : LINE}`,
            color: quotaExhausted ? '#8a4a3a' : MUTED,
            fontFamily: 'var(--font-mono)',
          }}
        >
          <span>
            {quota.used} of {quota.limit} audits used this month
          </span>
          <span>
            Resets {new Date(quota.resets_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </span>
        </div>
      )}
      {quotaExhausted && (
        <div
          className="mb-6 rounded-lg px-4 py-3 text-[13px]"
          style={{
            backgroundColor: 'rgba(206,145,120,0.06)',
            border: `1px dashed rgba(206,145,120,0.4)`,
            color: '#8a4a3a',
          }}
        >
          You've used both audits for this month. Upgrade to Matcha Lite for
          unlimited audits, or come back when the quota resets.
        </div>
      )}
      <div className="mb-7">
        <SectionLabel>Handbook PDF</SectionLabel>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="w-full rounded-xl px-5 py-8 text-left flex items-center gap-4 transition-colors"
          style={{
            backgroundColor: pdfFile ? 'rgba(31,29,26,0.04)' : 'rgba(31,29,26,0.02)',
            border: `1px dashed ${LINE}`,
            color: INK,
          }}
        >
          <UploadCloud className="w-7 h-7 shrink-0" style={{ color: MUTED }} />
          <div className="min-w-0">
            {pdfFile ? (
              <>
                <div className="text-sm font-medium truncate" style={{ color: INK }}>{pdfFile.name}</div>
                <div className="text-xs mt-1" style={{ color: MUTED }}>
                  {(pdfFile.size / 1024 / 1024).toFixed(2)} MB · click to choose another
                </div>
              </>
            ) : (
              <>
                <div className="text-sm font-medium" style={{ color: INK }}>Choose your handbook PDF</div>
                <div className="text-xs mt-1" style={{ color: MUTED }}>PDF only, up to 10MB</div>
              </>
            )}
          </div>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0] || null)}
        />
      </div>

      <div className="mb-7">
        <SectionLabel>
          State for this audit
          <span className="ml-2 normal-case tracking-normal" style={{ color: MUTED, fontFamily: 'var(--font-mono)' }}>
            {selectedState ?? '—'}
          </span>
        </SectionLabel>
        <p className="text-[12px] mb-3" style={{ color: MUTED }}>
          Each audit covers one state. Run another for your other locations.
        </p>
        <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
          {STATES.map((s) => {
            const isOn = selectedState === s.code
            return (
              <button
                key={s.code}
                type="button"
                onClick={() => setSelectedState(s.code)}
                title={s.name}
                className="h-9 rounded-md text-[12px] font-medium tracking-wide transition-colors"
                style={{
                  backgroundColor: isOn ? INK : 'rgba(31,29,26,0.04)',
                  color: isOn ? BG : INK,
                  border: `1px solid ${isOn ? INK : LINE}`,
                }}
              >
                {s.code}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mb-7">
        <SectionLabel>Industry</SectionLabel>
        <select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="w-full rounded-lg px-4 py-3 text-[15px]"
          style={{
            backgroundColor: 'rgba(31,29,26,0.02)',
            border: `1px solid ${LINE}`,
            color: INK,
          }}
        >
          {INDUSTRIES.map((i) => (
            <option key={i.value} value={i.value}>{i.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <div
          className="text-sm px-3 py-2 rounded-md mb-5"
          style={{
            color: '#8a4a3a',
            backgroundColor: 'rgba(206,145,120,0.1)',
            border: '1px solid rgba(206,145,120,0.3)',
          }}
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !pdfFile || !selectedState || quotaExhausted}
        className="w-full md:w-auto inline-flex items-center justify-center gap-2 px-7 h-12 rounded-full text-[14px] font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
        style={{ backgroundColor: INK, color: BG }}
      >
        {submitting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Uploading…
          </>
        ) : (
          <>
            <ShieldAlert className="w-4 h-4" />
            Run my gap audit
          </>
        )}
      </button>

      <p className="mt-5 text-[11px]" style={{ color: MUTED }}>
        Your handbook is stored privately and used only to generate this audit.
        Informational only — not legal advice.
      </p>
    </form>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="block text-[10.5px] uppercase tracking-[0.2em] font-mono mb-3"
      style={{ color: MUTED }}
    >
      {children}
    </div>
  )
}

function Pillar({ icon: Icon, title, body }: { icon: typeof UploadCloud; title: string; body: string }) {
  return (
    <div
      className="rounded-2xl p-6"
      style={{ backgroundColor: 'rgba(255,255,255,0.4)', border: `1px solid ${LINE}` }}
    >
      <Icon className="w-5 h-5 mb-3" style={{ color: INK }} />
      <h3
        className="tracking-tight mb-2"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.15rem', color: INK }}
      >
        {title}
      </h3>
      <p className="text-sm leading-relaxed" style={{ color: MUTED }}>{body}</p>
    </div>
  )
}
