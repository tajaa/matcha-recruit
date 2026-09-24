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

// Frosted glass, as in the Change section's chat: translucent white with a
// white inner rim, over faint matcha and amber glows.
const RIM = 'rgba(255, 255, 255, 0.85)'
const PANE = {
  backgroundColor: 'rgba(255, 255, 255, 0.5)',
  backdropFilter: 'blur(28px) saturate(1.5)',
  WebkitBackdropFilter: 'blur(28px) saturate(1.5)',
  boxShadow: `inset 0 0 0 1px ${RIM}, 0 0 0 1px ${hexA(INK, 0.05)}, 0 40px 80px -48px ${hexA(INK, 0.3)}`,
} as const

/** A result: dot + label on a pill tinted with the outcome's colour. The dot
 *  fills in as its row lands. */
function Result({ outcome, i }: { outcome: Outcome; i: number }) {
  const o = OUTCOME[outcome]
  return (
    <span
      className="inline-flex shrink-0 items-center gap-2 rounded-full px-2.5 py-1"
      style={{ ...mono('9px', { color: INK }), backgroundColor: hexA(o.dot, 0.09) }}
    >
      <span
        aria-hidden
        className="check-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ ['--dot' as string]: o.dot, ['--d' as string]: `${i * STEP + 350}ms` }}
      />
      {o.label}
    </span>
  )
}

/** One rule's line in the report: the rule, what it found on the demo week,
 *  and the result. No dividers — alternate rows carry a whisper of white. */
function Row({ rule, i }: { rule: (typeof RULES)[number]; i: number }) {
  const found = <span style={mono('10px', { color: INK_SOFT })}>{rule.example}</span>
  return (
    <Reveal
      as="li"
      delay={i * STEP}
      className="rounded-2xl px-4 py-3.5 lg:grid lg:grid-cols-12 lg:items-center lg:gap-x-6"
      style={{ backgroundColor: i % 2 ? 'transparent' : 'rgba(255, 255, 255, 0.4)' }}
    >
      <div className="lg:col-span-5">
        {/* phone: the result rides next to the rule's name */}
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[0.98rem] font-medium leading-snug tracking-[-0.015em]" style={{ color: INK }}>
            {rule.name}
          </h3>
          <span className="lg:hidden">
            <Result outcome={rule.outcome} i={i} />
          </span>
        </div>
        <p className="mt-0.5 text-[0.85rem] leading-[1.5]" style={{ color: INK_SOFT }}>
          {rule.detail}
        </p>
      </div>
      <div className="mt-2 lg:col-span-4 lg:mt-0">{found}</div>
      <div className="hidden lg:col-span-3 lg:flex lg:justify-end">
        <Result outcome={rule.outcome} i={i} />
      </div>
    </Reveal>
  )
}

/** The report the rule check produced on the demo week — output, like every
 *  other section, rather than a list of bullet points. */
function Report() {
  const counts = (Object.keys(OUTCOME) as Outcome[]).map((o) => ({ o, n: RULES.filter((r) => r.outcome === o).length }))
  return (
    <div className="relative mt-16">
      {/* glows for the glass to catch; inset so they fade inside the section */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background: [
            `radial-gradient(30% 40% at 18% 22%, ${hexA(STAMP, 0.16)}, transparent 70%)`,
            `radial-gradient(28% 36% at 82% 78%, ${hexA(AMBER, 0.14)}, transparent 70%)`,
          ].join(', '),
        }}
      />
      <div className="relative rounded-[28px] p-2 sm:p-3" style={PANE}>
        <div className="flex items-baseline justify-between gap-6 px-4 pb-3 pt-3" style={mono('9.5px', { color: INK_SOFT })}>
          <span>
            <span style={{ color: INK }}>Check report</span> · Sun 3:40 PM
          </span>
          <span>
            Week of Oct 5 · {RULES.length} rules
          </span>
        </div>
        <ol className="space-y-0.5">
          {RULES.map((rule, i) => (
            <Row key={rule.name} rule={rule} i={i} />
          ))}
        </ol>
        {/* the tally: three brighter panes */}
        <Reveal delay={RULES.length * STEP} className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {counts.map(({ o, n }) => (
            <div
              key={o}
              className="rounded-2xl px-4 py-3.5"
              style={{ backgroundColor: 'rgba(255, 255, 255, 0.7)', boxShadow: `inset 0 0 0 1px ${RIM}, 0 0 0 1px ${hexA(INK, 0.04)}` }}
            >
              <div className="flex items-center gap-2" style={mono('9.5px', { color: INK })}>
                <Dot color={OUTCOME[o].dot} />
                {n} {OUTCOME[o].label}
              </div>
              <p className="mt-1.5 text-[0.85rem] leading-snug" style={{ color: INK_SOFT }}>
                {OUTCOME[o].means}
              </p>
            </div>
          ))}
        </Reveal>
      </div>
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
