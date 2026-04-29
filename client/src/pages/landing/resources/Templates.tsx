import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Download, FileText } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'
import EmailGateModal from './EmailGateModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Asset = { slug: string; path: string; name: string }
type AssetList = { assets: Asset[] }

const TEMPLATE_DESCRIPTIONS: Record<string, string> = {
  'offer-letter-docx':
    'Editable offer letter covering compensation, start date, contingencies, and at-will language.',
  'offer-letter-pdf':
    'PDF version of the standard offer letter — print-ready, locked formatting.',
  'job-descriptions-library':
    '50+ ready-to-edit job descriptions across hospitality, healthcare, retail, and corporate roles.',
  'pip':
    'Performance Improvement Plan template with goals, metrics, and review cadence — vetted for legal defensibility.',
  'termination-checklist':
    'Step-by-step termination checklist covering offboarding, final pay, equipment return, and unemployment filings.',
  'i9-w4-packet':
    'New-hire compliance packet — I-9 + W-4 with completion guidance for HR.',
  'interview-scorecard':
    'Structured interview scorecard with competency rubrics — reduces bias claims and improves hiring quality.',
  'interview-guide':
    'What you can and can\'t legally ask in an interview. Covers age, childcare, transportation, marital status, disability, citizenship, and bona-fide-occupational-qualification exceptions (e.g., delivery roles requiring a license).',
  'pto-policy':
    'PTO policy template — accrual schedule, carryover, payout-on-termination, with state-specific notes.',
  'workplace-investigation-report':
    'Investigation report template — intake, witness interviews, findings, and recommended actions.',
}

const FORMAT_LABEL: Record<string, string> = {
  '.docx': 'DOCX',
  '.pdf': 'PDF',
}

function formatFor(path: string): string {
  const ext = path.slice(path.lastIndexOf('.'))
  return FORMAT_LABEL[ext] ?? ext.replace('.', '').toUpperCase()
}

export default function Templates() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [showPricing, setShowPricing] = useState(false)
  const [activeAsset, setActiveAsset] = useState<Asset | null>(null)

  useEffect(() => {
    api.get<AssetList>('/resources/assets')
      .then(d => setAssets(d.assets))
      .catch(() => setAssets([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10">
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to="/resources" className="hover:opacity-60">Resources</Link>
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

        {loading ? (
          <p style={{ color: MUTED }}>Loading templates…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {assets.map(asset => (
              <article
                key={asset.slug}
                className="p-6 rounded-2xl flex flex-col"
                style={{ border: `1px solid ${LINE}` }}
              >
                <div className="flex items-start justify-between mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(15,15,15,0.05)' }}
                  >
                    <FileText className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <span
                    className="text-[10px] tracking-wider px-2 py-1 rounded"
                    style={{ border: `1px solid ${LINE}`, color: MUTED }}
                  >
                    {formatFor(asset.path)}
                  </span>
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
                  onClick={() => setActiveAsset(asset)}
                  className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
                  style={{ backgroundColor: INK, color: BG }}
                >
                  <Download className="w-4 h-4" />
                  Download
                </button>
              </article>
            ))}
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

      <MarketingFooter />

      <EmailGateModal
        open={!!activeAsset}
        onClose={() => setActiveAsset(null)}
        asset={activeAsset}
      />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
