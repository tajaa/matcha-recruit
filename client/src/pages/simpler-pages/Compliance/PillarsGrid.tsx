import { motion } from 'framer-motion'

import { INSTRUMENTS } from './instruments'
import type { Pillar } from './types'
import { DISPLAY, GREEN_600, INK, LINE, MUTED } from './theme'

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

export function PillarsGrid() {
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
