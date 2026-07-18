import { Link } from 'react-router-dom'

import { ComplianceHeroAnimation } from '../../landing/ComplianceHeroAnimation'
import { BG, DISPLAY, GREEN, INK, MUTED } from './theme'

// ---------------------------------------------------------------------------
// Hero — dark stat panel, grayscale tiles, green underline as the one accent.
// ---------------------------------------------------------------------------

export function Hero({ onContactClick }: { onContactClick: () => void }) {
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
