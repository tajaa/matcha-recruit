import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Bell, ChevronRight, Download, FileText } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Asset = { slug: string; path: string; name: string; available: boolean }
type AssetList = { assets: Asset[] }

const TEMPLATE_DESCRIPTIONS: Record<string, string> = {
  'offer-letter':
    'Editable offer letter covering compensation, start date, contingencies, and at-will language.',
  'pip':
    'Performance Improvement Plan template with goals, metrics, and review cadence — vetted for legal defensibility.',
  'termination-checklist':
    'Step-by-step termination checklist covering offboarding, final pay, equipment return, and unemployment filings.',
  'interview-scorecard':
    'Structured interview scorecard with competency rubrics — reduces bias claims and improves hiring quality.',
  'interview-guide':
    'What you can and can\'t legally ask in an interview. Covers age, childcare, transportation, marital status, disability, citizenship, and bona-fide-occupational-qualification exceptions (e.g., delivery roles requiring a license).',
  'pto-policy':
    'PTO policy template — accrual schedule, carryover, payout-on-termination, with state-specific notes.',
  'workplace-investigation-report':
    'Investigation report template — intake, witness interviews, findings, and recommended actions.',
  'performance-review':
    'Annual + quarterly review template — goal scoring, competency ratings, manager + self-review sections, development plan.',
  'disciplinary-action':
    'Documented warning template — incident facts, policy violated, prior coaching, expectations, consequences. Builds the paper trail you need.',
  'remote-work-agreement':
    'Remote work agreement covering equipment, expenses, work hours, data security, workers\' comp scope, multi-state tax implications, and at-will revocation.',
  'expense-reimbursement':
    'Expense reimbursement form + policy — categories, receipts, per-diem rules, IRS-compliant accountable plan structure.',
  'severance-agreement':
    'Severance + release template with OWBPA-compliant ADEA waiver language, 21/45-day consideration period, and 7-day revocation. Customizable by tenure tier.',
  'i9-form':
    'Official Form I-9 (USCIS) — required for every new U.S. hire. Section 1 by employee on day 1; Section 2 by employer within 3 business days. Direct link to the latest USCIS edition.',
  'w4-form':
    'Official Form W-4 (IRS) — federal income tax withholding certificate. Direct link to the current IRS edition with One Big Beautiful Bill Act updates.',
}

const FORMAT_LABEL: Record<string, string> = {
  '.docx': 'DOCX',
  '.pdf': 'PDF',
}

function formatFor(path: string): string {
  const ext = path.slice(path.lastIndexOf('.'))
  return FORMAT_LABEL[ext] ?? ext.replace('.', '').toUpperCase()
}

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    cardBg: '#18181b', iconBg: '#27272a',
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)', iconBg: 'rgba(15,15,15,0.05)',
  }
}

export default function Templates({ embedded }: { embedded?: boolean }) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  useEffect(() => {
    api.get<AssetList>('/resources/assets')
      .then(d => setAssets(d.assets))
      .catch(() => setAssets([]))
      .finally(() => setLoading(false))
  }, [])

  const handleDownload = (asset: Asset) => {
    if (!asset.available) return
    // Cross-origin downloads (S3/CloudFront, government sites) ignore the
    // `download` attribute — open in a new tab so the browser saves DOCX
    // automatically and renders PDFs inline.
    window.open(asset.path, '_blank', 'noopener,noreferrer')
  }

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        {!embedded && (
          <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: t.muted }}>
            <Link to={root} className="hover:opacity-60">Resources</Link>
            <ChevronRight className="w-3 h-3" />
            <span style={{ color: t.ink }}>Templates</span>
          </nav>
        )}

        {embedded ? (
          <div className="mb-6">
            <h1 className="text-2xl font-semibold text-zinc-100">HR Templates</h1>
            <p className="mt-1 text-sm text-zinc-500">
              Free, editable templates for the documents HR teams use most. Reviewed against current employment-law guidance.
            </p>
          </div>
        ) : (
          <header className="mb-14 max-w-2xl">
            <h1
              className="text-5xl sm:text-6xl tracking-tight"
              style={{ fontFamily: t.display, fontWeight: 500, color: t.ink }}
            >
              HR Templates
            </h1>
            <p className="mt-4 text-base" style={{ color: t.muted }}>
              Free, editable templates for the documents HR teams use most.
              Drop in your details, send, file. Reviewed against current employment-law guidance.
            </p>
          </header>
        )}

        {/* Job Descriptions Library — separate browse page (62 roles) */}
        <Link
          to={`${root}/templates/job-descriptions`}
          className={embedded
            ? 'block mb-4 p-4 rounded-lg border border-zinc-800 hover:border-zinc-600 hover:bg-zinc-900/40 transition-colors'
            : 'block mb-6 p-6 rounded-2xl transition-opacity hover:opacity-80'}
          style={embedded ? undefined : { border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className={embedded ? 'text-[11px] uppercase tracking-wider mb-1 text-zinc-500' : 'text-xs uppercase tracking-wider mb-2'} style={embedded ? undefined : { color: t.muted }}>Library</p>
              <h2
                className={embedded ? 'text-base font-medium text-zinc-100 mb-1' : 'text-2xl mb-1'}
                style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}
              >
                Job Descriptions Library
              </h2>
              <p className={embedded ? 'text-xs text-zinc-500' : 'text-sm'} style={embedded ? undefined : { color: t.muted }}>
                Browse 62 ready-to-edit job descriptions across hospitality, healthcare,
                retail, corporate, and more.
              </p>
            </div>
            <ArrowUpRight className={embedded ? 'w-4 h-4 mt-1 flex-shrink-0 text-zinc-400' : 'w-5 h-5 mt-1 flex-shrink-0'} style={embedded ? undefined : { color: t.ink }} />
          </div>
        </Link>

        {loading ? (
          <p style={{ color: t.muted }}>Loading templates…</p>
        ) : (
          <div className={embedded ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3' : 'grid grid-cols-1 sm:grid-cols-2 gap-4'}>
            {assets.map(asset => {
              const available = asset.available
              if (embedded) {
                return (
                  <article
                    key={asset.slug}
                    className="p-4 rounded-lg border border-zinc-800 flex flex-col"
                    style={{ opacity: available ? 1 : 0.7 }}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="w-8 h-8 rounded-md bg-zinc-800 flex items-center justify-center">
                        <FileText className="w-4 h-4 text-zinc-300" />
                      </div>
                      <div className="flex items-center gap-1.5">
                        {!available && (
                          <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-zinc-800 text-zinc-500">
                            Soon
                          </span>
                        )}
                        <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-zinc-800 text-zinc-500">
                          {formatFor(asset.path)}
                        </span>
                      </div>
                    </div>
                    <h3 className="text-sm font-medium text-zinc-100 mb-1">{asset.name}</h3>
                    <p className="text-xs text-zinc-500 mb-4 flex-1 line-clamp-3">
                      {TEMPLATE_DESCRIPTIONS[asset.slug] ?? ''}
                    </p>
                    <button
                      onClick={() => handleDownload(asset)}
                      disabled={!available}
                      className={`inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium transition-colors ${
                        available
                          ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                          : 'border border-zinc-800 text-zinc-500'
                      }`}
                    >
                      {available ? (<><Download className="w-3.5 h-3.5" />Download</>) : (<><Bell className="w-3.5 h-3.5" />Notify</>)}
                    </button>
                  </article>
                )
              }
              return (
                <article
                  key={asset.slug}
                  className="p-6 rounded-2xl flex flex-col"
                  style={{ border: `1px solid ${t.line}`, opacity: available ? 1 : 0.92 }}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: t.iconBg }}
                    >
                      <FileText className="w-5 h-5" style={{ color: t.ink }} />
                    </div>
                    <div className="flex items-center gap-2">
                      {!available && (
                        <span
                          className="text-[10px] tracking-wider px-2 py-1 rounded"
                          style={{ border: `1px solid ${t.line}`, color: t.muted }}
                        >
                          COMING SOON
                        </span>
                      )}
                      <span
                        className="text-[10px] tracking-wider px-2 py-1 rounded"
                        style={{ border: `1px solid ${t.line}`, color: t.muted }}
                      >
                        {formatFor(asset.path)}
                      </span>
                    </div>
                  </div>

                  <h3
                    className="text-lg mb-2"
                    style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
                  >
                    {asset.name}
                  </h3>
                  <p className="text-sm mb-6 flex-1" style={{ color: t.muted }}>
                    {TEMPLATE_DESCRIPTIONS[asset.slug] ?? ''}
                  </p>

                  <button
                    onClick={() => handleDownload(asset)}
                    disabled={!available}
                    className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                    style={{
                      backgroundColor: available ? INK : 'transparent',
                      color: available ? BG : INK,
                      border: available ? 'none' : `1px solid ${LINE}`,
                    }}
                  >
                    {available ? (
                      <>
                        <Download className="w-4 h-4" />
                        Download
                      </>
                    ) : (
                      <>
                        <Bell className="w-4 h-4" />
                        Notify me when ready
                      </>
                    )}
                  </button>
                </article>
              )
            })}
          </div>
        )}

        {embedded ? (
          <section className="mt-8 p-5 rounded-lg border border-zinc-800 bg-zinc-900/30">
            <h2 className="text-base font-medium text-zinc-100 mb-1">Need state-specific versions?</h2>
            <p className="text-xs text-zinc-500 mb-4 max-w-2xl">
              Matcha generates templates tailored to your state's wage, leave,
              and termination rules — pulled from a live compliance database covering all 50 states.
            </p>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center justify-center px-4 h-8 rounded-md text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white"
            >
              See how Matcha works →
            </button>
          </section>
        ) : (
          <section
            className="mt-20 p-8 rounded-2xl"
            style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
          >
            <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
              Need state-specific versions?
            </h2>
            <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
              Matcha generates templates tailored to your state's wage, leave,
              and termination rules — pulled from a live compliance database
              covering all 50 states. Plus handbooks, policies, and offer letters
              customized to your business.
            </p>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center justify-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ backgroundColor: INK, color: BG }}
            >
              See how Matcha works →
            </button>
          </section>
        )}
      </main>

      {!embedded && <MarketingFooter />}

      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
