import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'

import { LazyMount } from '../../landing/LazyMount'
import { BG, DISPLAY, GREEN, INK, MUTED } from './theme'

const AgentReasoningAnimation = lazy(() => import('../../landing/AgentReasoningAnimation'))

// ---------------------------------------------------------------------------
// Hero — centered headline + CTAs over the live agent-reasoning panel.
// ---------------------------------------------------------------------------

export function Hero({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 70% 80% at 50% 30%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
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
              The full platform
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(2.25rem, 6vw, 5rem)',
            }}
          >
            One brain for the
            <br />
            whole <span style={{ fontStyle: 'italic' }}>risk</span> function.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Safety, compliance, and employee relations — usually three siloed
            systems. Matcha runs them on one platform where every signal talks
            to the others — so your real risk reads as a single live number, not
            twelve disconnected reports.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <button
              onClick={onContactClick}
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Book a consultation
            </button>
            <Link
              to="/services"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Explore services →
            </Link>
          </div>
        </div>

        {/* Live agent-reasoning panel — the platform's signature visual */}
        <div className="hidden sm:flex mt-12 sm:mt-16 w-full overflow-hidden justify-center">
          <LazyMount
            minHeight={600}
            fallback={<div className="w-full max-w-[1060px] mx-auto rounded-xl" style={{ height: 600, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}
          >
            <Suspense fallback={<div className="w-full max-w-[1060px] mx-auto rounded-xl" style={{ height: 600, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}>
              <AgentReasoningAnimation mono />
            </Suspense>
          </LazyMount>
        </div>
      </div>
    </section>
  )
}
