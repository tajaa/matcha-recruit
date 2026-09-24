import type { CSSProperties } from 'react'
import { Reveal } from '../motion'
import { WRAP, display, mono } from '../styles'
import { HILITE, INK, INK_SOFT, PAPER_DEEP, RED_PEN, STAMP, hexA } from '../theme'
import { Accent, StepHead } from './Chrome'

type Outcome = 'stops' | 'draft' | 'priced'

const OUTCOME: Record<Outcome, { label: string; means: string; style: CSSProperties }> = {
  stops: {
    label: 'Stops & asks you',
    means: 'Won’t save until you override it on purpose.',
    style: { color: RED_PEN, border: `1.5px solid ${RED_PEN}` },
  },
  draft: {
    label: 'Fixed in the draft',
    means: 'The draft is built around it before you see it.',
    style: { backgroundColor: HILITE, color: INK, border: `1.5px solid ${HILITE}` },
  },
  priced: {
    label: 'Priced in',
    means: 'Shows up in the week’s labor cost.',
    style: { color: STAMP, border: `1.5px solid ${STAMP}` },
  },
}

// Examples are the illustrative café's own week (hero + chat), so the page
// tells one story.
const RULES: { name: string; detail: string; example: string; outcome: Outcome }[] = [
  { name: 'Double-booking', detail: 'One person, two places at the same time.', example: 'Sam O. · Sat 7a–3p + 10a–6p', outcome: 'stops' },
  { name: 'Outside availability', detail: 'A shift outside the hours someone set.', example: 'Priya S. · Thursday · blocked', outcome: 'stops' },
  { name: 'Shift already full', detail: 'Headcount is met. One more is your call.', example: 'Sat open · 3 of 3 baristas', outcome: 'stops' },
  { name: 'Short turnaround', detail: 'Under 8 hours between a close and the next open.', example: 'Dev P. · Thu 11p → Fri 6a · 7h', outcome: 'draft' },
  { name: 'Weekly overtime', detail: 'Past 40 hours in the week — FLSA § 207(a).', example: 'Marisol V. · 44h', outcome: 'draft' },
  { name: 'Minor hour limits', detail: 'Weekly and daily caps for crew under 18.', example: 'Under 18 · school week', outcome: 'draft' },
  { name: 'Expired certifications', detail: 'A lapsed card or license on the day of the shift.', example: 'Kiko T. · food handler · exp Aug 30', outcome: 'draft' },
  { name: 'California daily overtime', detail: 'Past 8 and 12 hours in a day — Cal. Lab. Code § 510.', example: '10h shift · 2h at 1.5×', outcome: 'priced' },
]

function Mark({ outcome }: { outcome: Outcome }) {
  return (
    <span className="inline-flex whitespace-nowrap rounded-full px-3 py-1" style={mono('10px', { fontWeight: 700, ...OUTCOME[outcome].style })}>
      {OUTCOME[outcome].label}
    </span>
  )
}

export function Check() {
  return (
    <section id="check" style={{ backgroundColor: PAPER_DEEP }}>
      <div className={`${WRAP} grid grid-cols-1 gap-14 py-28 sm:py-44 lg:grid-cols-12 lg:gap-10`}>
        <div className="lg:col-span-5">
          <div className="lg:sticky lg:top-28">
            <StepHead
              step="check"
              title={
                <>
                  Checked <Accent>before</Accent>
                  <br className="hidden sm:block" /> it reaches you.
                </>
              }
            >
              Every rule below runs on the draft. The hard ones also stop a manual edit — drag a shift somewhere it shouldn’t go and Matcha asks
              first.
            </StepHead>
            <Reveal delay={240}>
              <dl className="mt-10 space-y-4">
                {(Object.keys(OUTCOME) as Outcome[]).map((o) => (
                  <div key={o} className="grid grid-cols-[10.5rem_1fr] items-center gap-4">
                    <dt>
                      <Mark outcome={o} />
                    </dt>
                    <dd className="text-[0.92rem] leading-snug" style={{ color: INK_SOFT }}>
                      {OUTCOME[o].means}
                    </dd>
                  </div>
                ))}
              </dl>
            </Reveal>
          </div>
        </div>

        <ol className="lg:col-span-7">
          {RULES.map((rule, i) => (
            <Reveal
              as="li"
              key={rule.name}
              delay={(i % 4) * 60}
              className="grid gap-3 py-7 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-8"
              style={{ borderTop: `1px solid ${hexA(INK, 0.2)}`, ...(i === RULES.length - 1 ? { borderBottom: `1px solid ${hexA(INK, 0.2)}` } : {}) }}
            >
              <div>
                <div style={{ ...display, fontSize: 'clamp(1.75rem, 3vw, 2.4rem)', lineHeight: 0.95 }}>{rule.name}</div>
                <p className="mt-2 text-[1rem] leading-[1.55]" style={{ color: INK_SOFT }}>
                  {rule.detail}
                </p>
                <div className="mt-3 inline-block pl-2.5" style={mono('10.5px', { color: INK, borderLeft: `2px solid ${RED_PEN}` })}>
                  {rule.example}
                </div>
              </div>
              <div className="sm:pt-1.5">
                <Mark outcome={rule.outcome} />
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
