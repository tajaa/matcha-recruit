import { BG, DISPLAY, GREEN_600, INK, LINE, MUTED } from './theme'

// ── Positioning — kept succinct: what the client sees vs. what you see ──────

export function Positioning() {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-2 gap-12 md:gap-20 items-start">
          <div className="max-w-md">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              The model
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              They get the platform. You get the signal.
            </h2>
          </div>
          <div className="grid sm:grid-cols-2 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                Your client sees
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Incident reporting</li>
                <li>Guided incident response</li>
                <li>Risk trends &amp; insights</li>
                <li>Pattern detection across cases</li>
              </ul>
            </div>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: GREEN_600 }}>
                You see
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Book-wide risk curve</li>
                <li>Loss-control ranking</li>
                <li>Risk alerts, ranked</li>
                <li>Outreach, AI-drafted</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
