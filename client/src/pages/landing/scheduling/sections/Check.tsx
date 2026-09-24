import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { INK, INK_SOFT, RED_PEN, STAMP, hexA } from '../theme'
import { Accent, StepHead } from './Chrome'

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

/** One band per outcome: what happens on the left, the rules it covers on the
 *  right. Grouped, not numbered — these are rules, not steps. */
function Band({ outcome, first }: { outcome: Outcome; first: boolean }) {
  const o = OUTCOME[outcome]
  const rules = RULES.filter((r) => r.outcome === outcome)
  return (
    <Reveal
      as="li"
      className={`grid grid-cols-1 gap-8 py-12 lg:grid-cols-12 lg:gap-10 ${first ? '' : 'border-t'}`}
      style={{ borderColor: RULE }}
    >
      <div className="lg:col-span-4">
        <div className="flex items-center gap-2.5" style={mono('10.5px', { color: INK })}>
          <Dot color={o.dot} />
          {o.label}
        </div>
        <p className="mt-3 max-w-[20rem] text-[0.97rem] leading-[1.6]" style={{ color: INK_SOFT }}>
          {o.means}
        </p>
      </div>
      <ul className="grid grid-cols-1 gap-x-10 gap-y-8 sm:grid-cols-2 lg:col-span-8">
        {rules.map((rule) => (
          <li key={rule.name}>
            <h3 className="text-[1.3rem] font-medium leading-tight tracking-[-0.02em]" style={{ color: INK }}>
              {rule.name}
            </h3>
            <p className="mt-1.5 text-[0.95rem] leading-[1.55]" style={{ color: INK_SOFT }}>
              {rule.detail}
            </p>
            <div className="mt-3" style={mono('10px', { color: INK_SOFT })}>
              e.g. <span style={{ color: INK }}>{rule.example}</span>
            </div>
          </li>
        ))}
      </ul>
    </Reveal>
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
      >
        Every rule below runs on the draft. The hard ones also stop a manual edit — drag a shift somewhere it shouldn’t go and Matcha asks first.
      </StepHead>

      <ol className="mt-16" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
        {(Object.keys(OUTCOME) as Outcome[]).map((o, i) => (
          <Band key={o} outcome={o} first={i === 0} />
        ))}
      </ol>
    </section>
  )
}
