import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'

// Decorative only, and it drags recharts (~100-150 KB gz, bundles d3) plus
// framer-motion onto a public marketing page. Lazy so the copy above the fold
// paints without waiting on a chart nobody navigated here to read.
const RiskInsightsHero = lazy(() =>
  import('../../../components/landing/RiskInsightsHero').then((m) => ({
    default: m.RiskInsightsHero,
  })),
)
import { BG, DISPLAY, GREEN, INK, MUTED } from './constants'

// ── Hero — clean centered statement, with a compact live intake instrument ──

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
              Built for daily use, not a once-a-year binder
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: GREEN,
              WebkitTextStroke: '1.5px #57534a',
              fontSize: 'clamp(2.25rem, 7vw, 5.25rem)',
            }}
          >
            Matcha Lite.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: '#4A463D', lineHeight: 1.55 }}
          >
            The everyday intake layer for your team — a magic link anyone can
            text, type into, or talk into. OSHA logs that fill themselves, risk
            insights from your own data, and a full HR library underneath.
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

        {/* Live risk-insights dashboard — the product's signature read. */}
        <div className="mt-12 sm:mt-16 max-w-5xl mx-auto -mx-2 sm:mx-auto">
          <div
            className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{ boxShadow: '0 40px 80px -25px rgba(31, 29, 26, 0.3)', borderColor: 'rgba(0,0,0,0.08)' }}
          >
            {/* Reserve the height so the lazy chunk landing doesn't shove the
                page down mid-read (CLS). */}
            <Suspense fallback={<div className="min-h-[420px]" />}>
              <RiskInsightsHero />
            </Suspense>
          </div>
        </div>
      </div>
    </section>
  )
}
