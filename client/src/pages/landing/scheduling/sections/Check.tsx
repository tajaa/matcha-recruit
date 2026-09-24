import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { AMBER, INK, INK_SOFT, STAMP, hexA } from '../theme'
import { Accent, StepHead } from './Chrome'

type Outcome = 'stops' | 'draft' | 'priced'

// One dot colour per outcome: amber waits on you, ink is handled for you,
// green is money on the week.
const OUTCOME: Record<Outcome, { label: string; means: string; dot: string }> = {
  stops: { label: 'Stops & asks you', means: 'Won’t save until you override it on purpose.', dot: AMBER },
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

const STEP = 70 // ms between rows ticking in

/** One rule's line in the report: the rule, what it found on the demo week,
 *  and the result. The dot fills in its outcome colour as the row lands. */
function Row({ rule, i }: { rule: (typeof RULES)[number]; i: number }) {
  const o = OUTCOME[rule.outcome]
  const result = (
    <span className="flex shrink-0 items-center gap-2.5 lg:justify-end" style={mono('10px', { color: INK })}>
      <span
        aria-hidden
        className="check-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ ['--dot' as string]: o.dot, ['--d' as string]: `${i * STEP + 350}ms` }}
      />
      {o.label}
    </span>
  )
  const found = <span style={mono('10.5px', { color: INK })}>{rule.example}</span>
  return (
    <Reveal as="li" delay={i * STEP} className="py-5 lg:grid lg:grid-cols-12 lg:items-baseline lg:gap-x-8" style={{ borderBottom: `1px solid ${RULE}` }}>
      <div className="lg:col-span-4">
        {/* phone: the result rides next to the rule's name */}
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-[1.05rem] font-medium leading-snug tracking-[-0.015em]" style={{ color: INK }}>
            {rule.name}
          </h3>
          <span className="lg:hidden">{result}</span>
        </div>
        <p className="mt-1 text-[0.9rem] leading-[1.5]" style={{ color: INK_SOFT }}>
          {rule.detail}
        </p>
      </div>
      {/* desktop: its own columns */}
      <div className="hidden lg:col-span-5 lg:block">{found}</div>
      <div className="hidden lg:col-span-3 lg:block">{result}</div>
      <div className="mt-3 lg:hidden">{found}</div>
    </Reveal>
  )
}

/** The report the rule check produced on the demo week — output, like every
 *  other section, rather than a list of bullet points. */
function Report() {
  const counts = (Object.keys(OUTCOME) as Outcome[]).map((o) => ({ o, n: RULES.filter((r) => r.outcome === o).length }))
  return (
    <div className="mt-16">
      <div className="flex items-baseline justify-between gap-6 pb-3" style={{ ...mono('10px', { color: INK_SOFT }), borderBottom: `1px solid ${RULE}` }}>
        <span>
          <span style={{ color: INK }}>Check report</span> · Sun 3:40 PM
        </span>
        <span>
          Week of Oct 5 · {RULES.length} rules
        </span>
      </div>
      <div className="hidden pb-2 pt-5 lg:grid lg:grid-cols-12 lg:gap-x-8" style={{ ...mono('9.5px', { color: INK_SOFT }), borderBottom: `1px solid ${RULE}` }}>
        <span className="lg:col-span-4">Rule</span>
        <span className="lg:col-span-5">Found on this draft</span>
        <span className="text-right lg:col-span-3">Result</span>
      </div>
      <ol>
        {RULES.map((rule, i) => (
          <Row key={rule.name} rule={rule} i={i} />
        ))}
      </ol>
      <Reveal delay={RULES.length * STEP} className="grid grid-cols-1 gap-6 pt-8 sm:grid-cols-3">
        {counts.map(({ o, n }) => (
          <div key={o}>
            <div className="flex items-center gap-2.5" style={mono('10.5px', { color: INK })}>
              <Dot color={OUTCOME[o].dot} />
              {n} {OUTCOME[o].label}
            </div>
            <p className="mt-2 max-w-[18rem] text-[0.92rem] leading-snug" style={{ color: INK_SOFT }}>
              {OUTCOME[o].means}
            </p>
          </div>
        ))}
      </Reveal>
    </div>
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
      <Report />
    </section>
  )
}
