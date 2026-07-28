import { lazy, Suspense } from 'react'
import { motion } from 'framer-motion'

import { LazyMount } from '../../landing/LazyMount'
import { PILLARS } from './data'
import { INSTRUMENTS } from './instruments'
import type { Pillar } from './types'
import { ASH, BONE } from '../../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

const AgentReasoningAnimation = lazy(() => import('../../landing/AgentReasoningAnimation'))

const REASONING_FALLBACK = (
  <div
    className="w-full max-w-[1060px] mx-auto rounded-xl"
    style={{ height: 600, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }}
  />
)

function PillarRow({ pillar, index }: { pillar: Pillar; index: number }) {
  const reverse = index % 2 === 1
  const Instrument = INSTRUMENTS[pillar.id]
  return (
    <section
      id={pillar.id}
      className={`relative overflow-hidden ${SECTION_Y}`}
    >
      <span
        className="absolute top-6 select-none pointer-events-none leading-none"
        style={{
          [reverse ? 'right' : 'left']: '-0.5rem',
          fontFamily: "var(--font-lite)",
          fontWeight: 300,
          fontSize: 'clamp(4.5rem, 10vw, 10rem)',
          color: BONE,
          opacity: 0.04,
        } as React.CSSProperties}
        aria-hidden
      >
        {pillar.number}
      </span>

      <div className={`relative ${CONTAINER}`}>
        <div className={`grid md:grid-cols-2 gap-12 lg:gap-24 items-center ${reverse ? 'md:[&>*:first-child]:order-2' : ''}`}>
          <motion.div
            className="max-w-xl"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="text-[12px] font-mk-mono uppercase tracking-[0.2em] mb-6" style={{ color: ASH }}>
              {pillar.number} · {pillar.title}
            </div>
            <h3
              className="tracking-tight"
              style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: BONE, fontSize: 'clamp(2rem, 3.4vw, 3.25rem)', lineHeight: 1.06 }}
            >
              {pillar.tagline}
            </h3>
            <p
              className="mt-6"
              style={{ fontFamily: "var(--font-lite)", fontStyle: 'italic', fontWeight: 300, color: BONE, fontSize: 'clamp(1.1rem, 1.5vw, 1.4rem)', lineHeight: 1.35 }}
            >
              <span style={{ color: ASH, opacity: 0.7 }}>"</span>
              {pillar.highlight}
              <span style={{ color: ASH, opacity: 0.7 }}>"</span>
            </p>
            <p className="mt-5 text-[16px] sm:text-lg max-w-md" style={{ color: ASH, lineHeight: 1.65 }}>
              {pillar.description}
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            {pillar.id === 'convergence' ? (
              <LazyMount minHeight={600} fallback={REASONING_FALLBACK}>
                <Suspense fallback={REASONING_FALLBACK}>
                  <AgentReasoningAnimation mono />
                </Suspense>
              </LazyMount>
            ) : (
              <Instrument />
            )}
          </motion.div>
        </div>
      </div>
    </section>
  )
}

export function PillarsGrid() {
  return (
    <>
      <section className="pt-20 sm:pt-28 pb-2">
        <div className={CONTAINER}>
          <Reveal>
            <div className="max-w-xl">
              <div className={EYEBROW} style={{ color: ASH, marginBottom: '1rem' }}>
                What it unifies
              </div>
              <h2
                className="tracking-tight"
                style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: BONE, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.08 }}
              >
                Three disciplines, one platform.
              </h2>
            </div>
          </Reveal>
        </div>
      </section>

      {PILLARS.map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i} />
      ))}
    </>
  )
}
