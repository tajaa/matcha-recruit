import { DISPLAY, INK, LINE, MUTED } from './theme'

// ---------------------------------------------------------------------------
// The point — a hard editorial cut before the close.
// ---------------------------------------------------------------------------

export function ThePoint() {
  return (
    <section className="py-24 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: MUTED }}>
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, lineHeight: 1.08, fontSize: 'clamp(2rem, 5vw, 4.25rem)' }}
        >
          We don’t hand you another dashboard. We run the whole risk and people
          function — safety, compliance, and the <span style={{ fontStyle: 'italic' }}>human</span> calls
          — on one brain.
        </p>
      </div>
    </section>
  )
}
