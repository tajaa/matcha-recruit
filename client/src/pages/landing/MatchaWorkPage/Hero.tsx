import { Link } from 'react-router-dom'

import { INK, BG, MUTED, DISPLAY } from './constants'

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

export function Hero() {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 100%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-10 pt-28 sm:pt-36 pb-12 sm:pb-16">
        <div className="text-center max-w-3xl mx-auto">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 sm:mb-8"
            style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#86efac' }} />
            <span className="text-[10px] sm:text-[11px] uppercase tracking-wider font-medium">
              AI-assisted workspace
            </span>
            <span
              className="text-[9px] uppercase tracking-wider font-medium px-1.5 py-[1px] rounded ml-1"
              style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}
            >
              Beta
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
            Your AI-assisted HR workspace.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-[15px] sm:text-base px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Live voice interviews and a multi-threaded document workspace — built for senior HR and compliance teams.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <Link
              to="/login"
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
              style={{ backgroundColor: INK, color: BG }}
            >
              Launch Workspace
            </Link>
            <Link
              to="/services"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Explore consulting →
            </Link>
          </div>
        </div>

      </div>
    </section>
  )
}
