import { ASH, BONE, DISPLAY, LEAF, LINE_D, SURFACE } from '../../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

// ── Positioning — kept succinct: what the client sees vs. what you see ──────

export function Positioning() {
  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="grid md:grid-cols-2 gap-12 md:gap-20 items-start">
            <div className="max-w-md">
              <div className={EYEBROW} style={{ color: ASH, marginBottom: '1rem' }}>
                The model
              </div>
              <h2
                className="tracking-tight"
                style={{ fontFamily: DISPLAY, fontWeight: 300, color: BONE, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.08 }}
              >
                They get the platform. You get the signal.
              </h2>
            </div>
            <div className="grid sm:grid-cols-2 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE_D }}>
              <div className="p-8" style={{ backgroundColor: SURFACE }}>
                <div className="text-[10.5px] font-mk-mono uppercase tracking-[0.2em] mb-4" style={{ color: ASH }}>
                  Your client sees
                </div>
                <ul className="space-y-2.5 text-[15px]" style={{ color: BONE }}>
                  <li>Incident reporting</li>
                  <li>Guided incident response</li>
                  <li>Risk trends &amp; insights</li>
                  <li>Pattern detection across cases</li>
                </ul>
              </div>
              <div className="p-8" style={{ backgroundColor: SURFACE }}>
                <div className="text-[10.5px] font-mk-mono uppercase tracking-[0.2em] mb-4" style={{ color: LEAF }}>
                  You see
                </div>
                <ul className="space-y-2.5 text-[15px]" style={{ color: BONE }}>
                  <li>Book-wide risk curve</li>
                  <li>Loss-control ranking</li>
                  <li>Risk alerts, ranked</li>
                  <li>Outreach, AI-drafted</li>
                </ul>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
