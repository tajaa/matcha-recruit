import { DISPLAY, INK, LINE, MUTED } from './theme'

// ---------------------------------------------------------------------------
// The point — a hard editorial cut before the close, same device as the
// platform page's manifesto, reset in the page's own ivory tokens.
// ---------------------------------------------------------------------------

export function ThePoint() {
  return (
    <section className="py-24 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span
          className="text-[11px] tracking-[0.3em] font-mono uppercase"
          style={{ color: MUTED }}
        >
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 400,
            color: INK,
            lineHeight: 1.08,
            fontSize: 'clamp(2rem, 5vw, 4.25rem)',
          }}
        >
          We don’t ship a checklist and disappear. We stay responsible for
          keeping it <span style={{ fontStyle: 'italic' }}>current</span> —
          so you’re never the one who finds out the hard way.
        </p>
      </div>
    </section>
  )
}
