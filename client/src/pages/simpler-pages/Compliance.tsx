import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Scale, Bell, FileText, Library, BadgeCheck, ListChecks } from 'lucide-react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/PricingContactModal'
import { ComplianceHeroAnimation } from '../landing/ComplianceHeroAnimation'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const GREEN = '#A3C57D' // the one emphasis color — everything else stays grayscale
const GREEN_600 = '#5B7F3E' // eyebrow labels specifically

// ---------------------------------------------------------------------------
// Simplified /compliance — same four-pillar product (jurisdictional
// compliance, handbook audit, policy management, credentialing) as the full
// page, told in outcome-level marketing copy only. No mechanism detail (no
// "preemption engine", no AI/OCR specifics, no data provenance) and no
// in-app mockups.
//
// Grayscale card system, one green accent used the same way on every card:
// it marks the single node each pillar resolves to — the governing rule,
// the critical gap, the active policy, the day a credential expires. That's
// the "shape strip", a chip row that traces each pillar's real structure
// instead of a generic bullet icon.
// ---------------------------------------------------------------------------

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  highlight: string
}

const PILLARS: Pillar[] = [
  {
    id: 'jurisdiction',
    number: '01',
    title: 'Jurisdictional Compliance',
    tagline: 'Every rule that governs each location, resolved.',
    description:
      'See what applies where you operate, federal down to city — and know the moment it changes.',
    highlight: 'Every rule, every location, always current.',
  },
  {
    id: 'handbook-audit',
    number: '02',
    title: 'Handbook Audit',
    tagline: 'Find the gaps before an auditor does.',
    description: 'Upload your handbook. We show you where it falls short of your state.',
    highlight: 'The gap analysis, without the consultant.',
  },
  {
    id: 'policy-management',
    number: '03',
    title: 'Policy Management',
    tagline: 'Draft, store, and keep policies current.',
    description: 'A living library that keeps every policy current, so nothing quietly goes stale.',
    highlight: 'A policy library that never goes stale.',
  },
  {
    id: 'credentialing',
    number: '04',
    title: 'Credentialing',
    tagline: 'The right credentials, tracked to the date.',
    description: 'Define what each role needs, and we keep watch on every employee’s dates for you.',
    highlight: 'No lapsed license discovered at audit time.',
  },
]

export default function SimpleCompliancePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <CoverageGrid />
        <ThePoint />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero — dark stat panel, grayscale tiles, green underline as the one accent.
// ---------------------------------------------------------------------------

function Hero({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 70% 80% at 85% 40%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-10 pt-28 sm:pt-36 pb-12 sm:pb-16">
        <div className="text-center max-w-3xl mx-auto">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 sm:mb-8"
            style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: GREEN }} />
            <span className="text-[10px] sm:text-[11px] uppercase tracking-wider font-medium">
              Standalone compliance platform
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(2.25rem, 7vw, 5.25rem)',
            }}
          >
            Matcha Compliance.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Compliance tracking, handbook audits, policies, and
            credentialing — one system your team actually runs on.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <button
              onClick={onContactClick}
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Talk to sales
            </button>
            <Link
              to="/resources"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Browse free resources →
            </Link>
          </div>
        </div>

        {/* Live compliance-monitor panel inside the hero frame */}
        <div className="mt-12 sm:mt-16 flex justify-center -mx-2 sm:mx-auto">
          <ComplianceHeroAnimation />
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pillars — four full-width editorial rows (≈ two pages of scroll), not a
// compact card grid. Each pillar alternates copy / instrument sides and gets
// its own bespoke grayscale diagram: a jurisdiction stack that resolves to
// the governing rule, a graded handbook, a policy lifecycle, a credential
// countdown. One green mark per instrument — the node it resolves to — and
// an oversized ghost numeral bleeding off the copy side. Grayscale else.
// ---------------------------------------------------------------------------

function PulseDot({ size = 8 }: { size?: number }) {
  return (
    <span className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <motion.span
        className="absolute rounded-full"
        style={{ width: size, height: size, backgroundColor: GREEN }}
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 0, 0.35] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="relative block rounded-full" style={{ width: size, height: size, backgroundColor: GREEN }} />
    </span>
  )
}

// 01 — a nested stack that narrows federal → city, resolving to the one
// governing rule (lit).
function JurisdictionInstrument() {
  const rows = [
    { label: 'Federal', w: 100, note: 'Baseline' },
    { label: 'State', w: 78, note: 'Overlay' },
    { label: 'County', w: 56, note: 'Overlay' },
    { label: 'City', w: 38, note: 'Governs', lit: true },
  ]
  return (
    <InstrumentFrame caption="Requirement stack" foot="Resolves to the one rule that governs">
      <div className="flex flex-col gap-3">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-4">
            <div className="w-16 shrink-0 text-[10px] font-mono uppercase tracking-wider text-right" style={{ color: r.lit ? INK : MUTED, fontWeight: r.lit ? 600 : 400 }}>
              {r.label}
            </div>
            <div className="relative flex-1 h-7">
              <div
                className="absolute inset-y-0 left-0 rounded-sm flex items-center px-2.5"
                style={{
                  width: `${r.w}%`,
                  border: `1px solid ${r.lit ? 'transparent' : LINE}`,
                  backgroundColor: r.lit ? GREEN : 'transparent',
                }}
              >
                <span
                  className="text-[9px] font-mono uppercase tracking-wider"
                  style={{ color: r.lit ? '#1a1408' : MUTED }}
                >
                  {r.note}
                </span>
              </div>
              {r.lit && (
                <span className="absolute -right-1 top-1/2 -translate-y-1/2" style={{ left: `${r.w}%` }}>
                  <PulseDot />
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </InstrumentFrame>
  )
}

// 02 — a graded handbook: section rows with grade marks, one flagged.
function HandbookInstrument() {
  const sections = [
    { label: 'At-will & EEO', w: 82, grade: 'ok' },
    { label: 'Meal & rest breaks', w: 64, grade: 'flag' },
    { label: 'Leave policies', w: 74, grade: 'ok' },
    { label: 'Anti-harassment', w: 58, grade: 'weak' },
    { label: 'Pay & overtime', w: 70, grade: 'ok' },
  ]
  const mark: Record<string, { t: string; c: string }> = {
    ok: { t: '✓', c: MUTED },
    weak: { t: '~', c: MUTED },
    flag: { t: 'CRITICAL', c: GREEN },
  }
  return (
    <InstrumentFrame caption="Handbook · graded" foot="Every section scored against your state">
      <div className="flex flex-col gap-3.5">
        {sections.map((s) => {
          const m = mark[s.grade]
          const lit = s.grade === 'flag'
          return (
            <div key={s.label} className="flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-[11px] mb-1.5" style={{ color: lit ? INK : MUTED, fontWeight: lit ? 600 : 400 }}>
                  {s.label}
                </div>
                <div className="h-1 rounded-full" style={{ width: `${s.w}%`, backgroundColor: lit ? GREEN : LINE }} />
              </div>
              {lit ? (
                <span className="flex items-center gap-1.5 shrink-0">
                  <PulseDot size={6} />
                  <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: m.c }}>{m.t}</span>
                </span>
              ) : (
                <span className="text-[11px] font-mono w-14 text-right shrink-0" style={{ color: m.c }}>{m.t}</span>
              )}
            </div>
          )
        })}
      </div>
    </InstrumentFrame>
  )
}

// 03 — a policy kept current, with a live review date. No lifecycle detail.
function PolicyInstrument() {
  return (
    <InstrumentFrame caption="Policy · lifecycle" foot="Next review tracked — never slips">
      <div className="flex flex-col items-center text-center gap-4 py-3">
        <PulseDot size={10} />
        <p style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.6rem', color: INK, lineHeight: 1.2 }}>
          Always current. Never stale.
        </p>
      </div>
      <div className="mt-6 pt-5 border-t flex items-center justify-between" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: MUTED }}>Next review</span>
        <span className="text-[12px] font-mono" style={{ color: INK }}>Mar 14 · 42 days</span>
      </div>
    </InstrumentFrame>
  )
}

// 04 — a credential countdown, expiry node lit.
function CredentialInstrument() {
  const marks = [
    { label: '90d', note: 'Reminder' },
    { label: '30d', note: 'Nudge' },
    { label: '0d', note: 'Expires', lit: true },
  ]
  return (
    <InstrumentFrame caption="Credential · countdown" foot="Flagged long before it lapses">
      <div className="flex flex-col gap-4">
        {marks.map((m) => (
          <div key={m.label} className="flex items-center gap-4">
            <div className="w-10 shrink-0 text-[13px] font-mono tabular-nums text-right" style={{ color: m.lit ? INK : MUTED, fontWeight: m.lit ? 600 : 400 }}>
              {m.label}
            </div>
            <div className="flex items-center gap-2.5 flex-1">
              {m.lit ? <PulseDot size={7} /> : <span className="block rounded-full" style={{ width: 6, height: 6, border: `1px solid ${LINE}` }} />}
              <div className="flex-1 h-px" style={{ backgroundColor: m.lit ? GREEN : LINE }} />
              <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: m.lit ? GREEN_600 : MUTED }}>{m.note}</span>
            </div>
          </div>
        ))}
      </div>
    </InstrumentFrame>
  )
}

// Shared inset frame for the instruments — the one place a bordered panel is
// warranted, since it reads as a device, not a feature box.
function InstrumentFrame({ caption, foot, children }: { caption: string; foot: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: LINE, backgroundColor: 'rgba(31,29,26,0.015)' }}>
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: MUTED }}>{caption}</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: MUTED }}>
          <PulseDot size={5} />
          Live
        </span>
      </div>
      <div className="px-5 py-6">{children}</div>
      <div className="px-5 py-3 border-t text-[10px] font-mono uppercase tracking-[0.12em]" style={{ borderColor: LINE, color: MUTED }}>
        {foot}
      </div>
    </div>
  )
}

const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  jurisdiction: JurisdictionInstrument,
  'handbook-audit': HandbookInstrument,
  'policy-management': PolicyInstrument,
  credentialing: CredentialInstrument,
}

function PillarRow({ pillar, index }: { pillar: Pillar; index: number }) {
  const reverse = index % 2 === 1
  const Instrument = INSTRUMENTS[pillar.id]
  return (
    <section
      id={pillar.id}
      className="relative overflow-hidden border-t py-20 sm:py-28"
      style={{ borderColor: LINE }}
    >
      {/* Ghost numeral — same figure as the eyebrow, given the whole margin. */}
      <span
        className="absolute top-6 select-none pointer-events-none leading-none"
        style={{
          [reverse ? 'right' : 'left']: '-0.5rem',
          fontFamily: DISPLAY,
          fontWeight: 300,
          fontSize: 'clamp(9rem, 20vw, 20rem)',
          color: INK,
          opacity: 0.035,
        } as React.CSSProperties}
        aria-hidden
      >
        {pillar.number}
      </span>

      <div className="relative max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className={`grid md:grid-cols-2 gap-12 lg:gap-24 items-center ${reverse ? 'md:[&>*:first-child]:order-2' : ''}`}>
          {/* Copy */}
          <motion.div
            className="max-w-xl"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="text-[12px] uppercase tracking-[0.2em] font-mono mb-6" style={{ color: GREEN_600 }}>
              {pillar.number} · {pillar.title}
            </div>
            <h3
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 3.4vw, 3.25rem)', lineHeight: 1.04 }}
            >
              {pillar.tagline}
            </h3>
            <p
              className="mt-6"
              style={{ fontFamily: DISPLAY, fontStyle: 'italic', fontWeight: 400, color: INK, fontSize: 'clamp(1.1rem, 1.5vw, 1.4rem)', lineHeight: 1.35 }}
            >
              <span style={{ color: MUTED, opacity: 0.55 }}>“</span>
              {pillar.highlight}
              <span style={{ color: MUTED, opacity: 0.55 }}>”</span>
            </p>
            <p className="mt-5 text-[16px] sm:text-lg max-w-md" style={{ color: MUTED, lineHeight: 1.65 }}>
              {pillar.description}
            </p>
          </motion.div>

          {/* Instrument */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <Instrument />
          </motion.div>
        </div>
      </div>
    </section>
  )
}

function PillarsGrid() {
  return (
    <>
      <section className="pt-20 sm:pt-28 pb-2 border-t" style={{ borderColor: LINE }}>
        <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
          <div className="max-w-xl">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              What’s inside
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              Four systems, one product.
            </h2>
          </div>
        </div>
      </section>

      {PILLARS.map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i} />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Coverage recap — a hairline feature grid summarizing everything the product
// covers at a glance, after the four detailed pillar rows. Icon tile + serif
// heading + caption, with a tiny grayscale corner glyph carrying one green
// mark (the same "resolves to one node" motif as the pillar instruments).
// ---------------------------------------------------------------------------

function GlyphStack() {
  return (
    <div className="flex flex-col items-end gap-1">
      {[16, 12, 9].map((w, i) => (
        <span key={w} className="h-[3px] rounded-full" style={{ width: w, backgroundColor: i === 2 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphPulse() {
  return <PulseDot size={7} />
}
function GlyphDoc() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[18, 14, 18, 11].map((w, i) => (
        <span key={i} className="h-[2px] rounded-full" style={{ width: w, backgroundColor: i === 1 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphLifecycle() {
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="rounded-full"
          style={{ width: 6, height: 6, backgroundColor: i === 1 ? GREEN : 'transparent', border: i === 1 ? 'none' : `1px solid ${LINE}` }}
        />
      ))}
    </div>
  )
}
function GlyphCountdown() {
  return (
    <div className="flex items-center gap-1">
      {[9, 7, 5].map((w, i) => (
        <span key={i} className="rounded-full" style={{ width: w, height: w, backgroundColor: i === 2 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphChecks() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="h-[2px] rounded-full" style={{ width: 12, backgroundColor: LINE }} />
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 0 ? GREEN : MUTED }} />
        </span>
      ))}
    </div>
  )
}

const COVERAGE: { id: string; icon: typeof Scale; title: string; caption: string; glyph: () => React.ReactElement }[] = [
  {
    id: 'jurisdiction',
    icon: Scale,
    title: 'Jurisdiction stack',
    caption: 'Everything that applies where you operate, in one place and always current.',
    glyph: GlyphStack,
  },
  {
    id: 'change',
    icon: Bell,
    title: 'Change alerts',
    caption: 'The law moves before you do — so you hear about it before it becomes a problem.',
    glyph: GlyphPulse,
  },
  {
    id: 'handbook',
    icon: FileText,
    title: 'Handbook audit',
    caption: 'See exactly where your handbook falls short of your state, in a report you can hand to counsel.',
    glyph: GlyphDoc,
  },
  {
    id: 'policy',
    icon: Library,
    title: 'Policy library',
    caption: 'Every policy kept current in one place, so nothing quietly goes out of date.',
    glyph: GlyphLifecycle,
  },
  {
    id: 'credential',
    icon: BadgeCheck,
    title: 'Credentialing',
    caption: 'The right credentials tracked to the date, flagged long before anything lapses.',
    glyph: GlyphCountdown,
  },
  {
    id: 'actions',
    icon: ListChecks,
    title: 'Owned actions',
    caption: 'Every gap becomes someone’s job with a due date — nothing sits unresolved.',
    glyph: GlyphChecks,
  },
]

function CoverageGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-3 sm:mb-4" style={{ color: MUTED }}>
            The whole stack
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Everything compliance, in one place.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Six capabilities, one system. Each stands on its own; together they
            cover the compliance surface a growing team can’t afford to miss.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {COVERAGE.map((f, i) => {
            const Icon = f.icon
            const Glyph = f.glyph
            return (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.08, ease: 'easeOut' }}
                className="p-6 sm:p-8 flex flex-col"
                style={{ backgroundColor: BG }}
              >
                <div className="flex items-start justify-between mb-5">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: 'rgba(31,29,26,0.06)' }}>
                    <Icon className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <div className="h-10 flex items-center">
                    <Glyph />
                  </div>
                </div>
                <h3 className="text-lg sm:text-xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
                  {f.title}
                </h3>
                <p className="text-sm" style={{ color: MUTED, lineHeight: 1.6 }}>
                  {f.caption}
                </p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// The point — a hard editorial cut before the close, same device as the
// platform page's manifesto, reset in the page's own ivory tokens.
// ---------------------------------------------------------------------------

function ThePoint() {
  return (
    <section className="py-24 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span
          className="text-[11px] tracking-[0.3em] font-mono uppercase"
          style={{ color: MUTED }}
        >
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 400,
            color: INK,
            lineHeight: 1.08,
            fontSize: 'clamp(2rem, 5vw, 4.25rem)',
          }}
        >
          We don’t ship a checklist and disappear. We stay responsible for
          keeping it <span style={{ fontStyle: 'italic' }}>current</span> —
          so you’re never the one who finds out the hard way.
        </p>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Closing CTA band
// ---------------------------------------------------------------------------

function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
        >
          See the whole compliance stack.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us where you operate and how many people you employ. We’ll
          walk you through the rest.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onContactClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Contact us
          </button>
        </div>
      </div>
    </section>
  )
}
