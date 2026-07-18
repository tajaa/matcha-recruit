import { BG, DISPLAY, INK, LINE, MUTED } from './theme'

// ---------------------------------------------------------------------------
// Closing CTA band
// ---------------------------------------------------------------------------

export function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
        >
          See the whole platform.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us where you operate and how your team is structured. We’ll walk
          you through the rest.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onContactClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Book a consultation
          </button>
        </div>
      </div>
    </section>
  )
}
