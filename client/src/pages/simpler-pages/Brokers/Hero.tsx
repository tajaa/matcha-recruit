import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { BAND_COLOR, RADAR_ROWS } from './data'
import type { RiskBand } from './types'
import { BG, DISPLAY, GREEN, INK, MUTED } from './theme'

export function Hero({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 70% 80% at 85% 40%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-6 sm:px-10 pt-36 pb-20">
        <div className="grid lg:grid-cols-[1.15fr_1fr] gap-12 lg:gap-20 items-center">
          <div className="max-w-xl">
            <div
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8"
              style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: GREEN }} />
              <span className="text-[11px] uppercase tracking-wider font-medium">
                For P&amp;C brokers
              </span>
            </div>
            <h1
              className="leading-[0.95] tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(2.75rem, 6vw, 5.25rem)',
              }}
            >
              The intelligence layer for your whole book.
            </h1>
            <p
              className="mt-6 max-w-lg"
              style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
            >
              Your clients run a live safety intake system. You get back what no
              carrier portal gives you — real-time TRIR, DART, and loss trends,
              plus risk alerts and suggested actions, across every account you
              manage.
            </p>
            <div className="mt-10 flex items-center gap-4 flex-wrap">
              <button
                onClick={onBookClick}
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: INK, color: BG }}
              >
                Book a Walkthrough
              </button>
            </div>
          </div>

          <BookRiskCurveCard />
        </div>
      </div>
    </section>
  )
}

// Animated hero card — kept from the original page (colorful risk bands).
function BookRiskCurveCard() {
  const ref = useRef(null)
  const inView = useInView(ref, { amount: 0.3 })

  const counts = RADAR_ROWS.reduce(
    (acc, r) => ({ ...acc, [r.band]: (acc[r.band] ?? 0) + 1 }),
    {} as Record<RiskBand, number>,
  )

  return (
    <div
      ref={ref}
      className="relative rounded-xl overflow-hidden border"
      style={{
        borderColor: 'rgba(0,0,0,0.08)',
        backgroundColor: '#0e0d0b',
        boxShadow: '0 40px 80px -20px rgba(31, 29, 26, 0.28)',
      }}
    >
      <div
        className="px-5 sm:px-6 py-4 flex items-center justify-between border-b"
        style={{ borderColor: 'rgba(255,255,255,0.06)' }}
      >
        <div className="flex items-center gap-2.5">
          <span className="relative flex w-2 h-2">
            <motion.span
              className="absolute inline-flex w-full h-full rounded-full"
              style={{ backgroundColor: '#6ee7a8' }}
              animate={inView ? { opacity: [0.6, 0, 0.6], scale: [1, 2.4, 1] } : { opacity: 0.6 }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
            />
            <span className="relative inline-flex w-2 h-2 rounded-full" style={{ backgroundColor: '#6ee7a8' }} />
          </span>
          <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
            Book Risk Curve
          </span>
        </div>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Book · 24 clients
        </span>
      </div>

      <div className="relative">
        <motion.div
          aria-hidden
          className="absolute inset-x-0 pointer-events-none z-10"
          style={{
            height: '38%',
            background:
              'linear-gradient(180deg, rgba(110,231,168,0) 0%, rgba(110,231,168,0.10) 50%, rgba(110,231,168,0) 100%)',
          }}
          animate={inView ? { top: ['-38%', '100%'] } : { top: '-38%' }}
          transition={{ duration: 3.4, repeat: Infinity, ease: 'linear' }}
        />

        <ul>
          {RADAR_ROWS.map((r, i) => {
            const volatile = r.band !== 'stable'
            return (
              <motion.li
                key={r.client}
                className="px-5 sm:px-6 py-3.5 flex items-center justify-between gap-3 border-b"
                style={{ borderColor: 'rgba(255,255,255,0.045)' }}
                initial={{ opacity: 0, y: 6 }}
                animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
                transition={{ duration: 0.5, delay: i * 0.12, ease: 'easeOut' }}
              >
                <div className="min-w-0">
                  <div className="text-[13px] truncate" style={{ color: 'rgba(245,242,237,0.92)' }}>
                    {r.client}
                  </div>
                  <div className="text-[11px] mt-0.5 font-mono" style={{ color: 'rgba(245,242,237,0.4)' }}>
                    {r.metric}
                  </div>
                </div>
                <div className="flex items-center gap-2.5 shrink-0">
                  <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.5)' }}>
                    {r.delta}
                  </span>
                  <motion.span
                    className="text-[9px] font-medium uppercase tracking-wider px-2 py-1 rounded"
                    style={{
                      color: BAND_COLOR[r.band],
                      backgroundColor: `${BAND_COLOR[r.band]}1f`,
                    }}
                    animate={inView && volatile ? { opacity: [1, 0.45, 1] } : { opacity: 1 }}
                    transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut', delay: i * 0.2 }}
                  >
                    {r.band}
                  </motion.span>
                </div>
              </motion.li>
            )
          })}
        </ul>
      </div>

      <div
        className="px-5 sm:px-6 py-3.5 flex items-center gap-4"
        style={{ backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        {(['critical', 'elevated', 'stable'] as RiskBand[]).map((band) => (
          <div key={band} className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: BAND_COLOR[band] }} />
            <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.55)' }}>
              {counts[band] ?? 0} {band}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
