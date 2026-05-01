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

export default function Templates({ embedded }: { embedded?: boolean }) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'

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
    <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[1100px] mx-auto px-6 sm:px-10`}>
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>Templates</span>
        </nav>

        <header className="mb-14 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            HR Templates
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            Free, editable templates for the documents HR teams use most.
            Drop in your details, send, file. Reviewed against current employment-law guidance.
          </p>
        </header>

        {/* Job Descriptions Library — separate browse page (50+ roles) */}
        <Link
          to={`${root}/templates/job-descriptions`}
          className="block mb-6 p-6 rounded-2xl transition-opacity hover:opacity-80"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wider mb-2" style={{ color: MUTED }}>Library</p>
              <h2 className="text-2xl mb-1" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
                Job Descriptions Library
              </h2>
              <p className="text-sm" style={{ color: MUTED }}>
                Browse 50+ ready-to-edit job descriptions across hospitality,
                healthcare, retail, corporate, and more. Pick the one you
                need — no bulk download.
              </p>
            </div>
            <ArrowUpRight className="w-5 h-5 mt-1 flex-shrink-0" style={{ color: INK }} />
          </div>
        </Link>

        {loading ? (
          <p style={{ color: MUTED }}>Loading templates…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {assets.map(asset => {
              const available = asset.available
              return (
                <article
                  key={asset.slug}
                  className="p-6 rounded-2xl flex flex-col"
                  style={{ border: `1px solid ${LINE}`, opacity: available ? 1 : 0.92 }}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: 'rgba(15,15,15,0.05)' }}
                    >
                      <FileText className="w-5 h-5" style={{ color: INK }} />
                    </div>
                    <div className="flex items-center gap-2">
                      {!available && (
                        <span
                          className="text-[10px] tracking-wider px-2 py-1 rounded"
                          style={{ border: `1px solid ${LINE}`, color: MUTED }}
                        >
                          COMING SOON
                        </span>
                      )}
                      <span
                        className="text-[10px] tracking-wider px-2 py-1 rounded"
                        style={{ border: `1px solid ${LINE}`, color: MUTED }}
                      >
                        {formatFor(asset.path)}
                      </span>
                    </div>
                  </div>

                  <h3
                    className="text-lg mb-2"
                    style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                  >
                    {asset.name}
                  </h3>
                  <p className="text-sm mb-6 flex-1" style={{ color: MUTED }}>
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

        <section
          className="mt-20 p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Need state-specific versions?
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
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
      </main>

      {!embedded && <MarketingFooter />}

      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
