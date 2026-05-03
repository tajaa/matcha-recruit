import { useEffect } from 'react'
import { Link, useParams, Navigate } from 'react-router-dom'
import { ChevronRight, Download } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import NewsletterSignup from '../../../components/NewsletterSignup'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { useMe } from '../../../hooks/useMe'
import { JOB_DESCRIPTIONS } from './jobDescriptionsData'
import { JD_CONTENT, EEO_STATEMENT } from './jobDescriptionsContent'
import { useState } from 'react'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    cardBg: '#18181b',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
    btnOutline: { border: '1px solid #3f3f46', color: '#e4e4e7' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)',
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
    btnOutline: { border: `1px solid ${LINE}`, color: INK } as React.CSSProperties,
  }
}

export default function JobDescriptionDetail({ embedded }: { embedded?: boolean }) {
  const { slug } = useParams<{ slug: string }>()
  const [showPricing, setShowPricing] = useState(false)
  const { me } = useMe()
  const isLoggedIn = !!me?.user
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  const jd = JOB_DESCRIPTIONS.find(j => j.slug === slug)
  const content = slug ? JD_CONTENT[slug] : undefined

  useEffect(() => {
    if (jd) document.title = `${jd.title} Job Description Template — Matcha`
  }, [jd])

  if (!jd || !content) return <Navigate to={`${root}/templates/job-descriptions`} replace />

  function handleDownload() {
    if (!jd?.downloadUrl) return
    if (!isLoggedIn) {
      const next = encodeURIComponent(`${root}/templates/job-descriptions/${jd.slug}`)
      window.location.href = `/auth/resources-signup?next=${next}`
      return
    }
    window.open(jd.downloadUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? 'max-w-[900px]' : 'pt-28 pb-20 max-w-[900px] mx-auto px-6 sm:px-10'}>
        {!embedded && (
          <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: t.muted }}>
            <Link to={root} className="hover:opacity-60">Resources</Link>
            <ChevronRight className="w-3 h-3" />
            <Link to={`${root}/templates`} className="hover:opacity-60">Templates</Link>
            <ChevronRight className="w-3 h-3" />
            <Link to={`${root}/templates/job-descriptions`} className="hover:opacity-60">Job Descriptions</Link>
            <ChevronRight className="w-3 h-3" />
            <span style={{ color: t.ink }}>{jd.title}</span>
          </nav>
        )}

        {embedded ? (
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
            <div className="flex-1">
              <Link to={`${root}/templates/job-descriptions`} className="text-xs text-vsc-text/40 hover:text-vsc-text/70 transition-colors mb-2 inline-flex items-center gap-1">
                ← Back to library
              </Link>
              <span className="inline-block text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-vsc-border text-vsc-text/40 mb-2 ml-2">
                {jd.industry}
              </span>
              <h1 className="text-2xl font-semibold text-vsc-text">{jd.title}</h1>
              <p className="mt-1 text-sm text-vsc-text/50">{jd.description}</p>
            </div>
            <button
              onClick={handleDownload}
              className="inline-flex items-center gap-1.5 px-4 h-9 rounded-lg text-sm font-medium whitespace-nowrap bg-zinc-700 hover:bg-zinc-600 text-white transition-colors"
            >
              <Download className="w-4 h-4" />
              Download DOCX
            </button>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6 mb-10">
            <div>
              <span
                className="inline-block text-[10px] tracking-wider uppercase px-2 py-1 rounded mb-3"
                style={{ border: `1px solid ${t.line}`, color: t.muted }}
              >
                {jd.industry}
              </span>
              <h1
                className="text-4xl sm:text-5xl tracking-tight"
                style={{ fontFamily: t.display, fontWeight: 500, color: t.ink }}
              >
                {jd.title}
              </h1>
              <p className="mt-3 text-sm" style={{ color: t.muted }}>{jd.description}</p>
            </div>
            <div className="shrink-0">
              <button
                onClick={handleDownload}
                className="inline-flex items-center gap-2 px-5 h-11 rounded-full text-sm font-medium whitespace-nowrap"
                style={t.btnPrimary}
              >
                <Download className="w-4 h-4" />
                {isLoggedIn ? 'Download DOCX' : 'Download DOCX (free)'}
              </button>
              {!isLoggedIn && (
                <p className="text-xs mt-2 text-center" style={{ color: t.muted }}>
                  Free account required
                </p>
              )}
            </div>
          </div>
        )}

        <article className={embedded ? 'flex flex-col gap-5' : 'flex flex-col gap-8'}>
          <JDSection t={t} heading="Job Summary" embedded={embedded}>
            <p className={embedded ? 'text-sm leading-relaxed text-vsc-text/70' : 'text-sm leading-relaxed'} style={embedded ? undefined : { color: t.ink }}>{content.summary}</p>
          </JDSection>

          <JDSection t={t} heading="Key Responsibilities" embedded={embedded}>
            <ul className="flex flex-col gap-1.5">
              {content.responsibilities.map((r, i) => (
                <li key={i} className={embedded ? 'flex items-start gap-2 text-sm text-vsc-text/70' : 'flex items-start gap-3 text-sm'} style={embedded ? undefined : { color: t.ink }}>
                  <span className="mt-1.5 w-1 h-1 rounded-full shrink-0 bg-zinc-500" />
                  {r}
                </li>
              ))}
            </ul>
          </JDSection>

          <JDSection t={t} heading="Requirements" embedded={embedded}>
            <ul className="flex flex-col gap-1.5">
              {content.requirements.map((r, i) => (
                <li key={i} className={embedded ? 'flex items-start gap-2 text-sm text-vsc-text/70' : 'flex items-start gap-3 text-sm'} style={embedded ? undefined : { color: t.ink }}>
                  <span className="mt-1.5 w-1 h-1 rounded-full shrink-0 bg-zinc-500" />
                  {r}
                </li>
              ))}
            </ul>
          </JDSection>

          <JDSection t={t} heading="Preferred Qualifications" embedded={embedded}>
            <ul className="flex flex-col gap-1.5">
              {content.preferred.map((r, i) => (
                <li key={i} className={embedded ? 'flex items-start gap-2 text-sm text-vsc-text/70' : 'flex items-start gap-3 text-sm'} style={embedded ? undefined : { color: t.ink }}>
                  <span className="mt-1.5 w-1 h-1 rounded-full shrink-0 bg-zinc-500" />
                  {r}
                </li>
              ))}
            </ul>
          </JDSection>

          <JDSection t={t} heading="Compensation & Benefits" embedded={embedded}>
            <p className={embedded ? 'text-sm leading-relaxed text-vsc-text/50' : 'text-sm leading-relaxed'} style={embedded ? undefined : { color: t.muted }}>
              Compensation is competitive and commensurate with experience. We offer a comprehensive benefits
              package including health, dental, vision, retirement savings, paid time off, and other benefits
              as described in the Employee Handbook. [Insert specific compensation range and benefits details.]
            </p>
          </JDSection>

          <JDSection t={t} heading="Equal Opportunity Employer" embedded={embedded}>
            <p className={embedded ? 'text-sm leading-relaxed text-vsc-text/50' : 'text-sm leading-relaxed'} style={embedded ? undefined : { color: t.muted }}>{EEO_STATEMENT}</p>
          </JDSection>
        </article>

        {!embedded && (
          <>
            <div
              className="mt-12 p-6 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
              style={{ border: `1px solid ${t.line}` }}
            >
              <div>
                <p className="text-sm font-medium mb-1" style={{ color: t.ink, fontFamily: t.display }}>
                  Download the editable DOCX
                </p>
                <p className="text-xs" style={{ color: t.muted }}>
                  Free account • No card • DOCX file ready to customize
                </p>
              </div>
              <button
                onClick={handleDownload}
                className="inline-flex items-center gap-2 px-5 h-10 rounded-full text-sm font-medium shrink-0"
                style={t.btnPrimary}
              >
                <Download className="w-4 h-4" />
                {isLoggedIn ? 'Download DOCX' : 'Get free download'}
              </button>
            </div>

            <section
              className="mt-10 p-8 rounded-2xl"
              style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
            >
              <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
                Matcha keeps your HR compliant
              </h2>
              <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
                Job descriptions are just the start. Matcha tracks employment law across all 50 states,
                manages employee records, and automates incident reporting — so your HR team stays ahead
                of what the law requires.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link
                  to="/signup"
                  className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
                  style={t.btnPrimary}
                >
                  Get started free →
                </Link>
                <button
                  onClick={() => setShowPricing(true)}
                  className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
                  style={t.btnOutline}
                >
                  Talk to sales
                </button>
              </div>
            </section>
            <div className="mt-10">
              <NewsletterSignup
                source="job_descriptions"
                variant="card"
                headline="More HR templates, every week."
                description="Subscribe for new JDs, calculators, and employment-law briefs."
              />
            </div>
          </>
        )}
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}

function JDSection({ t, heading, children, embedded }: { t: ReturnType<typeof mkT>; heading: string; children: React.ReactNode; embedded?: boolean }) {
  if (embedded) {
    return (
      <section>
        <h2 className="text-xs uppercase tracking-wider font-medium text-vsc-text/40 mb-2 pb-1.5 border-b border-vsc-border">
          {heading}
        </h2>
        {children}
      </section>
    )
  }
  return (
    <section>
      <h2
        className="text-xl mb-4 pb-2"
        style={{
          fontFamily: t.display, color: t.ink, fontWeight: 500,
          borderBottom: `1px solid ${t.line}`,
        }}
      >
        {heading}
      </h2>
      {children}
    </section>
  )
}
