import { Link } from 'react-router-dom'

import { INK, BG, MUTED, LINE, DISPLAY } from './constants'

// ---------------------------------------------------------------------------
// Closing CTA
// ---------------------------------------------------------------------------

export function ClosingCta({ onPricingClick }: { onPricingClick: () => void }) {
  return (
    <section className="py-16 sm:py-24 md:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight max-w-2xl mx-auto"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.5rem)', lineHeight: 1.05 }}
        >
          Ready to put it to work?
        </h2>
        <p className="mt-4 sm:mt-5 max-w-xl mx-auto text-base sm:text-lg" style={{ color: MUTED }}>
          Launch the workspace or book a walkthrough with our team.
        </p>
        <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
          <Link
            to="/login"
            className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: INK, color: BG }}
          >
            Launch Workspace
          </Link>
          <button
            onClick={onPricingClick}
            className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
            style={{ color: INK }}
          >
            Request pricing →
          </button>
        </div>
      </div>
    </section>
  )
}
