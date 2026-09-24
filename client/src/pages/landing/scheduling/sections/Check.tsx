import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { INK, INK_SOFT, RED_PEN, STAMP, hexA } from '../theme'
import { Accent, CellLabel, StepHead } from './Chrome'

type Outcome = 'stops' | 'draft' | 'priced'

// One dot colour per outcome, same vocabulary as the hero sheet: red is the
// thing that stops you, ink is handled for you, green is money on the week.
const OUTCOME: Record<Outcome, { label: string; means: string; dot: string }> = {
  stops: { label: 'Stops & asks you', means: 'Won’t save until you override it on purpose.', dot: RED_PEN },
  draft: { label: 'Fixed in the draft', means: 'The draft is built around it before you see it.', dot: INK },
  priced: { label: 'Priced in', means: 'Shows up in the week’s labor cost.', dot: STAMP },
}

const RULE = hexA(INK, 0.1)

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

function Dot({ color }: { color: string }) {
  return <span aria-hidden className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
}

function Key() {
  return (
    <dl className="mt-8 space-y-3">
      {(Object.keys(OUTCOME) as Outcome[]).map((o) => (
        <div key={o} className="grid grid-cols-[10rem_1fr] items-baseline gap-4">
          <dt className="flex items-center gap-2" style={mono('10px', { color: INK })}>
            <Dot color={OUTCOME[o].dot} />
            {OUTCOME[o].label}
          </dt>
          <dd className="text-[0.92rem] leading-snug" style={{ color: INK_SOFT }}>
            {OUTCOME[o].means}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function Check() {
  return (
    <section id="check" className={`${WRAP} py-28 sm:py-44`}>
      <StepHead
        split
        step="check"
        title={
          <>
            Checked <Accent>before</Accent> it reaches you.
          </>
        }
        aside={<Key />}
      >
        Every rule below runs on the draft. The hard ones also stop a manual edit — drag a shift somewhere it shouldn’t go and Matcha asks first.
      </StepHead>

      {/* the Draft grid's hairline cells, two across */}
      <ol className="mt-16 grid grid-cols-1 lg:grid-cols-2" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
        {RULES.map((rule, i) => {
          const left = i % 2 === 0
          return (
            <Reveal
              as="li"
              key={rule.name}
              delay={left ? 0 : 100}
              className={`flex flex-col py-10 ${i ? 'border-t' : ''} ${i === 1 ? 'lg:border-t-0' : ''} ${left ? 'lg:border-r lg:pr-14' : 'lg:pl-14'}`}
              style={{ borderColor: RULE }}
            >
              <CellLabel n={String(i + 1).padStart(2, '0')}>
                <span className="inline-flex items-center gap-2">
                  <Dot color={OUTCOME[rule.outcome].dot} />
                  {OUTCOME[rule.outcome].label}
                </span>
              </CellLabel>
              <h3 className="mt-5 text-[1.45rem] font-medium leading-tight tracking-[-0.025em]" style={{ color: INK }}>
                {rule.name}
              </h3>
              <p className="mt-2 max-w-[26rem] text-[0.97rem] leading-[1.6]" style={{ color: INK_SOFT }}>
                {rule.detail}
              </p>
              <div className="mt-5" style={mono('10px', { color: INK_SOFT })}>
                e.g. <span style={{ color: INK }}>{rule.example}</span>
              </div>
            </Reveal>
          )
        })}
      </ol>
    </section>
  )
}
