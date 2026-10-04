import { useState, type ReactNode } from 'react'
import { ArrowRight, Check, ChevronDown } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, glassChip, glassPane, mono } from '../../../../components/marketing/kit/styles'
import { AMBER, INK, INK_SOFT, PAPER, SERIF, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, Glows, PrimaryButton } from '../sections/Chrome'
import { SCHEDULING_SIGNUP_PATH } from '../signup'

export function BuyerHeading({ label, eyebrow, title, children, dark = false }: { label: string; eyebrow: string; title: ReactNode; children: ReactNode; dark?: boolean }) {
  return (
    <div className="grid gap-6 lg:grid-cols-12 lg:items-end lg:gap-10">
      <div className="lg:col-span-7">
        <Reveal>
          <div className="flex flex-wrap items-center gap-3" style={mono('11px', { color: dark ? PAPER : INK })}>
            <span>{eyebrow}</span><span aria-hidden className="h-px w-8" style={{ backgroundColor: hexA(dark ? PAPER : INK, 0.25) }} />
            <span style={{ color: dark ? hexA(PAPER, 0.6) : INK_SOFT }}>{label}</span>
          </div>
        </Reveal>
        <Reveal delay={80}><h2 className="mt-6 max-w-[16ch]" style={{ ...display, fontSize: 'clamp(2.4rem, 5vw, 4.4rem)' }}>{title}</h2></Reveal>
      </div>
      <Reveal delay={160} className="lg:col-span-5 lg:pb-2"><p className="max-w-[34rem] text-[1.075rem] leading-[1.65]" style={{ color: dark ? hexA(PAPER, 0.72) : INK_SOFT }}>{children}</p></Reveal>
    </div>
  )
}

export function BuyerTopBar() {
  return (
    <div className="sticky top-0 z-50" style={{ backgroundColor: hexA(PAPER, 0.94), backdropFilter: 'blur(14px)', borderBottom: `1px solid ${hexA(INK, 0.1)}` }}>
      <div className={`${WRAP} flex h-16 items-center justify-between gap-3`}>
        <Link to="/" className="sched-focus rounded" aria-label="Matcha scheduling">
          <span style={{ ...display, fontSize: 21, fontWeight: 600 }}>Matcha</span>
        </Link>
        <nav aria-label="Product" className="flex items-center gap-3 sm:gap-5" style={mono('10.5px')}>
          <Link to="/" aria-current="page" className="sched-focus rounded" style={{ color: STAMP }}>Scheduling</Link>
          <Link to="/incidents" className="sched-link sched-focus rounded">Incidents</Link>
        </nav>
        <nav aria-label="Buying guide" className="hidden items-center gap-6 lg:flex" style={mono('10.5px')}>
          <a href="#setup" className="sched-link sched-focus rounded">Setup</a>
          <a href="#value" className="sched-link sched-focus rounded">Value</a>
          <a href="#pricing" className="sched-link sched-focus rounded">Pricing</a>
          <a href="#questions" className="sched-link sched-focus rounded">Questions</a>
        </nav>
        <div className="flex items-center gap-5">
          <Link to="/login" className="sched-link sched-focus rounded text-sm max-[359px]:hidden">Log in</Link>
          <Link to={SCHEDULING_SIGNUP_PATH} className="sched-btn sched-btn-ink sched-focus hidden h-10 items-center rounded-full px-4 text-sm font-medium sm:inline-flex">Start now</Link>
        </div>
      </div>
    </div>
  )
}

export function BuyerGuide() {
  return (
    <div style={{ borderBottom: `1px solid ${hexA(INK, 0.12)}` }}>
      <div className={`${WRAP} py-7`}>
        <div className="flex flex-wrap items-center justify-between gap-5">
          <a href="#pricing" className="sched-link sched-focus rounded text-base font-medium">Plans from $49 / location / month <span className="ml-2 text-xs font-normal" style={{ color: INK_SOFT }}>Pricing preview</span></a>
          <nav aria-label="Explore scheduling" className="flex flex-wrap gap-x-6 gap-y-3" style={mono('10px')}>
            <a href="#draft" className="sched-link sched-focus rounded">How it works</a>
            <a href="#setup" className="sched-link sched-focus rounded">Connect &amp; switch</a>
            <a href="#recovery" className="sched-link sched-focus rounded">When plans change</a>
            <a href="#fit" className="sched-link sched-focus rounded">Your operation</a>
          </nav>
        </div>
      </div>
    </div>
  )
}

const CONNECTIONS = [
  { name: 'Square sales', status: 'Supported with setup', detail: 'Import finalized sales orders. Map your Square locations and items so the forecast uses the right store’s sales.' },
  { name: 'CSV imports', status: 'Supported', detail: 'Bring your employee roster and sales exports. Employee bulk imports can include pay rates with a pay classification; review the file and store mapping first.' },
  { name: 'Other POS systems', status: 'Confirm your export', detail: 'A compatible sales CSV may work without a direct connection. A native Toast connection is not available today.' },
] as const

const SETUP = [
  { title: 'Bring your crew', detail: 'Add your locations, import employees, and confirm where each person works.' },
  { title: 'Set the week’s rules', detail: 'Set opening hours, jobs, availability, qualifications, and the coverage you need.' },
  { title: 'Add planning inputs', detail: 'Load sales history and pay rates for forecasting and scheduled labor cost.' },
  { title: 'Review your first week', detail: 'Check the draft, fix open seats and findings, then publish when you are ready.' },
] as const

export function Setup({ onContact }: { onContact: () => void }) {
  return (
    <section id="setup" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="Before week one" label="Connect & switch" title={<>Your crew. Your systems. A better <Accent>start.</Accent></>}>
        Start with the systems and files you already have. Confirm the connection, clean up the inputs, and build a week you can review.
      </BuyerHeading>
      <div className="mt-16 grid border-y lg:grid-cols-2" style={{ borderColor: hexA(INK, 0.12) }}>
        <Reveal className="py-10 sm:py-12 lg:pr-14">
          <CellLabel n="01">What comes with you</CellLabel>
          <div className="mt-8">
            {CONNECTIONS.map((connection, i) => (
              <div key={connection.name} className="py-7 first:pt-0 [&+div]:border-t" style={{ borderColor: hexA(INK, 0.1) }}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-2">
                  <h3 className="text-[1.5rem] font-medium tracking-[-0.025em]">{connection.name}</h3>
                  <span className="flex items-center gap-2" style={mono('9px', { color: INK_SOFT })}><span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: i === 2 ? AMBER : STAMP }} />{connection.status}</span>
                </div>
                <p className="mt-3 max-w-md text-[0.95rem] leading-[1.65]" style={{ color: INK_SOFT }}>{connection.detail}</p>
              </div>
            ))}
          </div>
        </Reveal>
        <Reveal delay={120} className="border-t py-10 sm:py-12 lg:border-l lg:border-t-0 lg:pl-14" style={{ borderColor: hexA(INK, 0.12) }}>
          <CellLabel n="02">The path to published</CellLabel>
          <ol className="mt-9 space-y-8">
            {SETUP.map((step, i) => (
              <li key={step.title} className="grid grid-cols-[44px_1fr] gap-5">
                <span aria-hidden style={{ fontFamily: SERIF, fontStyle: 'italic', fontSize: 48, lineHeight: 1, color: hexA(STAMP, 0.6) }}>{i + 1}</span>
                <div><h3 className="text-lg font-medium tracking-[-0.02em]">{step.title}</h3><p className="mt-2 max-w-sm text-sm leading-[1.65]" style={{ color: INK_SOFT }}>{step.detail}</p></div>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
      <Reveal className="mt-8 flex flex-wrap items-center justify-between gap-6">
        <p className="max-w-xl text-sm leading-[1.65]" style={{ color: INK_SOFT }}>Bring a roster, a recent schedule, and a sales export. We can check the format and discuss the help your rollout needs.</p>
        <PrimaryButton onClick={onContact}>Walk through my setup</PrimaryButton>
      </Reveal>
    </section>
  )
}

const RECOVERY = [
  {
    id: 'callout', label: 'A callout', title: 'Sam can’t make Saturday.', subtitle: 'Saturday · 7 AM–3 PM · one barista seat to refill',
    rows: [
      { name: 'Priya S.', result: 'Unavailable', detail: 'Outside her confirmed availability.', eligible: false },
      { name: 'Marisol V.', result: 'At her weekly cap', detail: 'No room for this shift under the store’s policy.', eligible: false },
      { name: 'Dev P.', result: 'Eligible for review', detail: 'Available, qualified, and has room in the week.', eligible: true },
    ],
    next: 'Review a replacement proposal, including coverage and scheduled cost, before confirming the change.',
  },
  {
    id: 'open-seat', label: 'An unfilled shift', title: 'The leader seat stays open.', subtitle: 'Friday · 4–11 PM · one qualified leader needed',
    rows: [
      { name: 'Kiko T.', result: 'Credential expired', detail: 'Not eligible for the required qualification on this date.', eligible: false },
      { name: 'Dev P.', result: 'Already assigned', detail: 'Would overlap another shift.', eligible: false },
      { name: 'Priya S.', result: 'Unavailable', detail: 'No confirmed availability for this window.', eligible: false },
    ],
    next: 'See why nobody fits. Resolve the roster or availability issue, or offer the published open seat for a manager-approved claim.',
  },
  {
    id: 'break-coverage', label: 'Break coverage', title: 'Two breaks. One thin floor.', subtitle: 'Saturday · midday · overlapping planned breaks',
    rows: [
      { name: '12:00–12:30', result: 'Coverage gap', detail: 'Both planned breaks would leave the floor short.', eligible: false },
      { name: 'Stagger the plan', result: 'Suggestion for review', detail: 'Separate the breaks within the applicable planning windows.', eligible: true },
      { name: 'Check relief', result: 'Manager action', detail: 'If coverage is still thin, arrange qualified relief before publishing.', eligible: false },
    ],
    next: 'Review break timing and relief together. Planning a break and sending a reminder do not verify that it was taken.',
  },
] as const

export function Recovery() {
  const [selected, setSelected] = useState(0)
  const example = RECOVERY[selected]
  return (
    <section id="recovery" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="During the week" label="When plans change" title={<>A rough shift. A clearer <Accent>next move.</Accent></>}>
        A schedule needs to survive the week. See who can cover, why a seat remains open, and where a break needs relief—with every change still in your hands.
      </BuyerHeading>
      <div className="mt-16 grid gap-10 lg:grid-cols-12 lg:gap-16">
        <Reveal className="lg:col-span-4">
          <div role="group" aria-label="Staffing examples" className="border-t" style={{ borderColor: hexA(INK, 0.15) }}>
            {RECOVERY.map((item, i) => (
              <button key={item.id} type="button" aria-pressed={selected === i} aria-controls="staffing-example" onClick={() => setSelected(i)} className="group sched-focus flex min-h-20 w-full items-center justify-between gap-4 border-b py-6 text-left transition-colors" style={{ borderColor: hexA(INK, 0.15), color: selected === i ? INK : INK_SOFT }}>
                <span className="flex items-baseline gap-5"><span style={mono('10px', { color: selected === i ? STAMP : INK_SOFT })}>0{i + 1}</span><span className="text-xl tracking-[-0.025em]" style={{ fontWeight: selected === i ? 500 : 400 }}>{item.label}</span></span>
                <ArrowRight size={17} className="shrink-0 transition-transform group-hover:translate-x-1" style={{ opacity: selected === i ? 1 : 0.35 }} aria-hidden />
              </button>
            ))}
          </div>
          <p className="mt-6 max-w-xs text-sm leading-[1.65]" style={{ color: INK_SOFT }}>Illustrative reviews. Eligibility depends on your roster, policies, and applicable rules.</p>
        </Reveal>
        <Reveal delay={120} className="relative min-w-0 lg:col-span-8">
          <Glows green="20% 30%" amber="82% 70%" className="-inset-10" />
          <div id="staffing-example" role="region" aria-label="Staffing review example" aria-live="polite" className="relative rounded-[28px] p-3 sm:p-4" style={glassPane}>
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3" style={mono('9px', { color: INK_SOFT })}>
              <span>Example · manager review</span><span className="flex items-center gap-2"><span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: AMBER }} />Needs review</span>
            </div>
            <div className="px-4 pb-5 pt-6">
              <h3 className="text-[clamp(1.6rem,3vw,2.3rem)] font-medium leading-[1.1] tracking-[-0.035em]">{example.title}</h3>
              <p className="mt-3 text-sm" style={{ color: INK_SOFT }}>{example.subtitle}</p>
            </div>
            <ul className="space-y-1">
              {example.rows.map((row, i) => (
                <li key={row.name} className="grid gap-2 rounded-2xl px-4 py-5 sm:grid-cols-[1fr_1.4fr] sm:gap-5" style={{ backgroundColor: i % 2 === 0 ? 'rgba(255,255,255,0.4)' : 'transparent' }}>
                  <div className="text-[0.95rem] font-medium tracking-[-0.015em]">{row.name}</div>
                  <div>
                    <div className="flex items-center gap-2 text-sm font-medium"><span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: row.eligible ? STAMP : AMBER }} />{row.result}</div>
                    <p className="mt-1 text-[0.85rem] leading-relaxed" style={{ color: INK_SOFT }}>{row.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-3 rounded-2xl p-5" style={glassChip}>
              <p className="flex items-center gap-2" style={mono('9px', { color: STAMP })}><ArrowRight size={13} aria-hidden />Next move</p>
              <p className="mt-2 text-sm leading-[1.65]" style={{ color: INK_SOFT }}>{example.next}</p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

const FIT = [
  { label: 'Local inputs · shared crew', title: 'More than one store', detail: 'Keep location-specific hours, jobs, demand, and rules in one business. Check overlapping assignments when employees work across stores.' },
  { label: 'Location rules + your policies', title: 'Rules for your location', detail: 'Review applicable scheduling guidance alongside your own policies. Coverage varies by jurisdiction; the review identifies missing or unavailable rule coverage.' },
  { label: 'Missing inputs stay visible', title: 'History that’s still growing', detail: 'When sales or weather are missing, the draft uses usual published hours when enough history exists, or your coverage floor. Missing inputs stay visible for review.' },
] as const

export function OperationFit() {
  return (
    <section id="fit" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="Across locations" label="Your operation" title={<>One business. Every store’s <Accent>details.</Accent></>}>
        Your second location should not inherit the first store’s assumptions. Keep the inputs local and the shared crew’s conflicts in view.
      </BuyerHeading>
      <div className="mt-16 grid border-y md:grid-cols-3" style={{ borderColor: hexA(INK, 0.12) }}>
        {FIT.map((item, i) => (
          <Reveal key={item.title} delay={i * 100} className="py-10 sm:py-12 [&+div]:border-t md:[&+div]:border-l md:[&+div]:border-t-0 md:[&+div]:pl-8 md:[&:not(:last-child)]:pr-8" style={{ borderColor: hexA(INK, 0.12) }}>
            <CellLabel n={`0${i + 1}`}>{['The crew', 'The policies', 'The inputs'][i]}</CellLabel>
            <h3 className="mt-8 max-w-[14ch] text-[1.75rem] font-medium leading-[1.1] tracking-[-0.035em]">{item.title}</h3>
            <p className="mt-5 text-[0.95rem] leading-[1.7]" style={{ color: INK_SOFT }}>{item.detail}</p>
            <p className="mt-8 flex items-center gap-2" style={mono('9px', { color: STAMP })}><Check size={13} className="shrink-0" aria-hidden />{item.label}</p>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

const QUESTIONS = [
  { question: 'Does Matcha replace my time clock or payroll?', answer: 'Today, Matcha plans shifts and breaks and projects scheduled labor cost. Native clock-in/out, actual-break verification, and timesheet payroll export are not available. Keep your existing timekeeping and payroll system; a Square sales connection imports sales, not employee punches.' },
  { question: 'Which compliance checks apply to my business?', answer: 'That depends on your locations, workforce, and the rules available for those jurisdictions. Reviews distinguish scheduling rules from company policies and identify coverage gaps. Fair Workweek exposure reporting currently covers New York City and Los Angeles. Your team reviews the findings and remains responsible for compliance.' },
  { question: 'Can I bring employees and pay rates from another system?', answer: 'You can import employee CSVs, with pay rates and pay classifications supported in the employee bulk import. Initial signup imports the roster first; add wage data for labor costing afterward. HRIS connections are available separately for supported providers; confirm the provider and plan before relying on a sync.' },
  { question: 'What happens if there isn’t enough data—or nobody can fill a shift?', answer: 'The draft names missing inputs and shows open seats with the reasons people could not be assigned. You can review a simpler plan, correct availability or qualification records, and request coverage. Matcha does not invent sales history or treat an unstaffed shift as a completed plan.' },
  { question: 'Can we add incidents, handbooks, or broader compliance?', answer: 'Those workflows are available elsewhere in Matcha. They are separately scoped for your business and are not included automatically in the scheduling plans shown here. Discuss the modules, data, and implementation your team needs.' },
] as const

export function BuyerQuestions({ onContact }: { onContact: () => void }) {
  return (
    <section id="questions" className={`${WRAP} py-28 sm:py-44`} style={{ borderTop: `1px solid ${hexA(INK, 0.12)}` }}>
      <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
        <Reveal className="lg:col-span-4">
          <p style={mono('11px', { color: INK_SOFT })}>Before you decide</p>
          <h2 className="mt-5" style={{ ...display, fontSize: 'clamp(2.4rem, 4vw, 3.8rem)' }}>The practical <Accent>questions.</Accent></h2>
          <button type="button" onClick={onContact} className="sched-link sched-focus mt-7 inline-flex items-center gap-2 rounded text-sm font-medium">Talk through your setup <ArrowRight size={15} aria-hidden /></button>
        </Reveal>
        <div className="lg:col-span-8">
          {QUESTIONS.map((item) => (
            <details key={item.question} className="group py-6" style={{ borderTop: `1px solid ${hexA(INK, 0.15)}` }}>
              <summary className="sched-focus flex cursor-pointer list-none items-center justify-between gap-5 rounded text-base font-medium [&::-webkit-details-marker]:hidden">
                {item.question}<ChevronDown className="shrink-0 transition-transform group-open:rotate-180" size={18} aria-hidden />
              </summary>
              <p className="mt-4 max-w-2xl text-[0.95rem] leading-[1.7]" style={{ color: INK_SOFT }}>{item.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
