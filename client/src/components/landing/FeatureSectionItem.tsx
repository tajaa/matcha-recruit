import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { DOT_GRID_BG } from './shared'
import { GlitchText } from '../GlitchText'

export interface Section {
  category: string
  accent: string
  title: string
  desc: string
  graphic: React.ComponentType
}

/* shared spring for snappy feel */
const SPRING = { type: 'spring' as const, stiffness: 80, damping: 20 }

export function FeatureSectionItem({ section, idx, isLast }: { section: Section, idx: number, isLast?: boolean }) {
  const reversed = idx % 2 === 1
  const Graphic = section.graphic
  const containerRef = useRef<HTMLDivElement>(null)
  const isInView = useInView(containerRef, { once: true, margin: '-10% 0px -10% 0px' })


  return (
    <section
      ref={containerRef}
      id={idx === 0 ? 'features' : undefined}
      className="relative border-t border-zinc-700/40 min-h-0 md:min-h-screen flex items-center py-16 sm:py-24 px-4 sm:px-8 overflow-hidden group md:snap-start"
    >
      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
      />

      <div className="relative z-10 max-w-7xl mx-auto w-full grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
        {/* Text block */}
        <motion.div
          className={reversed ? 'lg:order-2' : ''}
          style={{ willChange: 'transform, opacity' }}
          initial={false}
          animate={isInView
            ? { opacity: 1, y: 0 }
            : { opacity: 0, y: 24 }
          }
          transition={SPRING}
        >
          <motion.div
            className="flex items-center gap-2 mb-5"
            initial={false}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
            transition={{ ...SPRING, delay: 0.05 }}
          >
            <span className="h-1.5 w-1.5 rounded-full shadow-md" style={{ backgroundColor: section.accent, boxShadow: `0 0 10px ${section.accent}` }} />
            <span className="text-xs tracking-[0.3em] uppercase text-zinc-500">
              {section.category}
            </span>
          </motion.div>

          <motion.h2
            className="text-3xl sm:text-4xl font-bold uppercase tracking-wide text-zinc-100 mb-5 flex items-center gap-3"
            initial={false}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
            transition={{ ...SPRING, delay: 0.1 }}
          >
            <GlitchText text={section.title} className="inline-block drop-shadow-lg" />
          </motion.h2>

          <motion.p
            className="text-base text-zinc-400 leading-relaxed max-w-md"
            initial={false}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
            transition={{ ...SPRING, delay: 0.18 }}
          >
            {section.desc}
          </motion.p>

          <motion.div
            className="mt-8 h-px"
            style={{ background: `linear-gradient(90deg, ${section.accent}, transparent)`, transformOrigin: 'left' }}
            initial={false}
            animate={isInView ? { scaleX: 1, opacity: 0.5 } : { scaleX: 0, opacity: 0 }}
            transition={{ ...SPRING, delay: 0.25 }}
          />
        </motion.div>

        {/* Graphic */}
        <motion.div
          className={reversed ? 'lg:order-1' : ''}
          style={{ willChange: 'transform, opacity' }}
          initial={false}
          animate={isInView
            ? { opacity: 1, y: 0, scale: 1 }
            : { opacity: 0, y: 30, scale: 0.95 }
          }
          transition={{ ...SPRING, delay: 0.08 }}
        >
          <div
            className="relative border border-zinc-800/60 bg-zinc-950/40 overflow-hidden rounded-xl transition-all duration-500 hover:border-zinc-700/80 hover:shadow-2xl hover:-translate-y-1"
            style={{ boxShadow: isInView ? `0 25px 60px -12px rgba(0,0,0,0.6), 0 0 40px -8px ${section.accent}15` : 'none' }}
          >
            <Graphic />
          </div>
        </motion.div>
      </div>

      {/* Scroll indicator or CTA */}
      <div className="hidden md:block absolute bottom-6 left-1/2 -translate-x-1/2 z-20">
        {isLast ? (
          <motion.a
            href="/login"
            initial={false}
            animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
            transition={{ ...SPRING, delay: 0.4 }}
            className="inline-block uppercase text-sm tracking-[0.2em] px-10 py-3 border border-zinc-600 hover:border-zinc-400 text-zinc-300 hover:text-zinc-100 transition-colors duration-300 rounded-sm"
            style={{ fontFamily: '"Space Mono", monospace' }}
          >
            Initialize Account
          </motion.a>
        ) : (
          <div className="flex flex-col items-center gap-1 animate-pulse">
            <span
              className="text-[9px] uppercase text-zinc-600"
              style={{ fontFamily: '"Space Mono", monospace', letterSpacing: '0.2em' }}
            >
              Scroll
            </span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-zinc-600">
              <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}
      </div>
    </section>
  )
}
