import { ArrowDown, ArrowRight, Code2, GitBranch, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Accent, CellLabel, PrimaryButton } from '../../components/marketing/kit/Chrome'
import { Reveal } from '../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../components/marketing/kit/styles'
import { BOARD, INK, INK_SOFT, PAPER, STAMP, hexA } from '../../components/marketing/kit/theme'
import { TopBar } from './scheduling/sections/Chrome'
import { useHashScroll } from './scheduling/useHashScroll'
import BusinessSupportPreview from './BusinessSupportPreview'
import { IncidentsPreview, SchedulingPreview } from './BusinessSoftwarePreviews'

const SERVICES = [
  {
    id: 'hr', n: '01', label: 'Human resources', icon: Users,
    title: 'Take care of your people.',
    description: 'From your next hire to the conversations that can’t wait. Practical HR support for the everyday decisions and the difficult ones.',
    work: [
      ['Compliance', 'Handbooks, policies, and compliance support as your team and locations grow.'],
      ['Employee relations', 'Workplace concerns, investigations, and clear, consistent documentation.'],
      ['Hiring', 'Role definition, recruiting workflows, and onboarding that gives people a good start.'],
    ],
  },
  {
    id: 'operations', n: '02', label: 'Operations', icon: GitBranch,
    title: 'Make the everyday work better.',
    description: 'We get into the details of how your business runs, find what slows it down, and build a better way to get the work done.',
    work: [
      ['Workflow optimization', 'Map the process, remove bottlenecks, and simplify the handoffs.'],
      ['Systems & automation', 'Connect your tools and reduce the repetitive work between them.'],
      ['Processes that last', 'Clear playbooks, ownership, and training your team can put into practice.'],
    ],
  },
  {
    id: 'technology', n: '03', label: 'Technology solutions', icon: Code2,
    title: 'Build what your business needs.',
    description: 'A better website. More secure systems. Software that fits how you work. We help you choose, build, and put the right technology to use.',
    work: [
      ['Websites & custom software', 'Customer-facing websites and purpose-built tools for your team.'],
      ['Security', 'Review access, strengthen systems, and build safer day-to-day practices.'],
      ['Closed AI systems', 'Private AI workflows built around your business, with defined data access and controls.'],
    ],
  },
] as const

export default function BusinessHome({ onContact }: { onContact: () => void }) {
  useHashScroll()
  return (
    <>
      <a href="#main-content" className="sched-focus sr-only z-[70] rounded-full px-5 py-3 text-sm font-medium focus:not-sr-only focus:fixed focus:left-4 focus:top-4" style={{ backgroundColor: PAPER, color: INK }}>Skip to content</a>
      <TopBar tab="home" onContact={onContact} />
      <main id="main-content">
        <section className="sched-dark -mt-[112px] pt-[112px] md:-mt-16 md:pt-16" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
          <div className={`${WRAP} pb-10 pt-10 sm:pb-12 sm:pt-14 lg:pt-16`}>
            <div className="grid gap-12 lg:grid-cols-12 lg:items-center lg:gap-14">
              <div className="min-w-0 lg:col-span-7">
                <div className="flex items-center gap-3 cut-fade" style={mono('10px', { color: BOARD.INK_SOFT })}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.STAMP }} />
                  For growing businesses
                </div>
                <h1 className="mt-6 cut-fade" style={{ ...display, fontSize: 'clamp(3.3rem, 6.3vw, 5.8rem)' }}>
                  <span className="block">You grow.</span>
                  We get to <Accent dark>work.</Accent>
                </h1>
                <p className="mt-7 max-w-[30rem] text-[17px] leading-relaxed cut-fade" style={{ color: hexA(PAPER, 0.7) }}>
                  Hands-on HR, operations, and technology for growing businesses. We support your people, improve your workflows, and build the systems you need.
                </p>
                <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-5 cut-fade">
                  <PrimaryButton tone="paper" onClick={onContact}>Book a consultation</PrimaryButton>
                  <a href="#services" className="sched-link sched-focus inline-flex items-center gap-2 rounded text-sm">Explore what we do <ArrowDown size={15} /></a>
                </div>
              </div>
              <div className="min-w-0 lg:col-span-5 cut-fade">
                <BusinessSupportPreview />
              </div>
            </div>
            <div className="mt-12 flex flex-wrap items-center justify-between gap-x-10 gap-y-4 border-t pt-6" style={{ borderColor: hexA(PAPER, 0.16) }}>
              <span style={mono('9px', { color: BOARD.INK_SOFT })}>Expert help + purpose-built software</span>
              <div className="flex flex-wrap gap-x-7 gap-y-3 text-sm">
                <Link to="/scheduling" className="sched-link sched-focus rounded">Explore Scheduling ↗</Link>
                <Link to="/incidents" className="sched-link sched-focus rounded">Explore Incident Reporting ↗</Link>
              </div>
            </div>
          </div>
        </section>

        <section id="services" className={`${WRAP} py-20 sm:py-28`} aria-labelledby="services-title">
          <Reveal className="grid gap-6 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-7">
              <CellLabel n="01">What we do</CellLabel>
              <h2 id="services-title" className="mt-6 max-w-[16ch]" style={{ ...display, fontSize: 'clamp(2.6rem, 5vw, 4.5rem)' }}>Three ways to move<br /><Accent>forward.</Accent></h2>
            </div>
            <p className="max-w-md text-lg leading-relaxed lg:col-span-5" style={{ color: INK_SOFT }}>Start where you need us most. A single project or support across the business, with a clear scope and work you can put to use.</p>
          </Reveal>
          <div className="mt-12 grid border-y md:grid-cols-3" style={{ borderColor: hexA(INK, 0.18) }}>
            {SERVICES.map((service, i) => (
              <article key={service.id} id={service.id}
                className={`flex flex-col border-b py-9 last:border-b-0 md:border-b-0 md:py-10 ${i > 0 ? 'md:border-l md:pl-7 lg:pl-9' : ''} ${i < 2 ? 'md:pr-7 lg:pr-9' : ''}`}
                style={{ borderColor: hexA(INK, 0.16) }}>
                <Reveal className="flex h-full flex-col">
                  <div className="flex items-center justify-between gap-4">
                    <CellLabel n={service.n}>{service.label}</CellLabel>
                    <service.icon size={19} strokeWidth={1.3} style={{ color: STAMP }} />
                  </div>
                  <h3 className="mb-4 mt-6 max-w-[18ch] md:min-h-[2.2em]" style={{ ...display, fontSize: 'clamp(1.9rem, 2.7vw, 2.5rem)', lineHeight: 1.06 }}>{service.title}</h3>
                  <p className="text-[15px] leading-relaxed md:min-h-[6em]" style={{ color: INK_SOFT }}>{service.description}</p>
                  <dl className="mb-8 mt-7 space-y-5">
                    {service.work.map(([title, copy]) => (
                      <div key={title}>
                        <dt className="text-[14px] font-medium">{title}</dt>
                        <dd className="mt-1 text-[14px] leading-relaxed" style={{ color: INK_SOFT }}>{copy}</dd>
                      </div>
                    ))}
                  </dl>
                  <button type="button" onClick={onContact} className="sched-link sched-focus mt-auto inline-flex self-start items-center gap-2 rounded text-sm font-medium">Talk to us about {service.id === 'hr' ? 'HR' : service.id} <ArrowRight size={16} /></button>
                </Reveal>
              </article>
            ))}
          </div>
        </section>

        <section id="approach" className="sched-dark py-20 sm:py-24" style={{ backgroundColor: BOARD.PAPER, color: PAPER }} aria-labelledby="approach-title">
          <div className={WRAP}>
            <Reveal><CellLabel n="02" dark>How we work</CellLabel><h2 id="approach-title" className="mt-6 max-w-[20ch]" style={{ ...display, fontSize: 'clamp(2.6rem, 5vw, 4.5rem)' }}>Find the friction.<br />Then <Accent dark>fix it.</Accent></h2></Reveal>
            <div className="mt-14 grid gap-10 md:grid-cols-3 md:gap-12">
              {[
                ['01 / Understand', 'Start with your reality.', 'Tell us what’s working, what’s getting in the way, and where you want to go. We look at the whole workflow before recommending a solution.'],
                ['02 / Build', 'Put the plan to work.', 'We agree on priorities and scope, then help implement the process, people support, or technology that moves the work forward.'],
                ['03 / Support', 'Make it work for your team.', 'Documentation, training, and a clear handoff. When you need ongoing help, we can keep working alongside you.'],
              ].map(([label, title, copy]) => (
                <Reveal key={label} className="border-t pt-6" style={{ borderColor: hexA(PAPER, 0.2) }}>
                  <span style={mono('10px', { color: BOARD.STAMP })}>{label}</span>
                  <h3 className="mb-4 mt-5 text-2xl tracking-tight">{title}</h3>
                  <p className="text-base leading-relaxed" style={{ color: hexA(PAPER, 0.65) }}>{copy}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section id="software" className={`${WRAP} py-20 sm:py-28`} aria-labelledby="software-title">
          <Reveal className="grid gap-6 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-7"><CellLabel n="03">Our software</CellLabel><h2 id="software-title" className="mt-6 max-w-[17ch]" style={{ ...display, fontSize: 'clamp(2.6rem, 5vw, 4.5rem)' }}>Good tools.<br />Lighter <Accent>workdays.</Accent></h2></div>
            <p className="max-w-md text-lg leading-relaxed lg:col-span-5" style={{ color: INK_SOFT }}>Explore Matcha’s scheduling and incident reporting software, each with its own focused workflow. Use the tools you need alongside the support that fits.</p>
          </Reveal>
          <div className="mt-12 grid border-y md:grid-cols-2" style={{ borderColor: hexA(INK, 0.18) }}>
            <Link to="/scheduling" aria-label="Explore Scheduling" className="group sched-focus border-b py-8 transition-colors duration-200 hover:bg-[#18211B]/[0.025] motion-reduce:transition-none md:border-b-0 md:border-r md:pr-8 lg:pr-10 sm:py-10" style={{ borderColor: hexA(INK, 0.18) }}>
              <CellLabel n="01">Scheduling</CellLabel>
              <h3 className="mt-6 text-3xl tracking-tight transition-colors group-hover:text-[#3F6B2A] motion-reduce:transition-none">Next week, under control.</h3>
              <p className="mt-4 max-w-md leading-relaxed md:min-h-[4.5em]" style={{ color: INK_SOFT }}>Draft the week around demand and availability. Check coverage, overtime, and labor costs before you publish.</p>
              <div className="my-7"><SchedulingPreview /></div>
              <span className="inline-flex items-center gap-3 text-sm font-medium">Explore Scheduling <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></span>
            </Link>
            <Link to="/incidents" aria-label="Explore Incident Reporting" className="group sched-focus py-8 transition-colors duration-200 hover:bg-[#18211B]/[0.025] motion-reduce:transition-none md:pl-8 lg:pl-10 sm:py-10">
              <CellLabel n="02">Incident reporting</CellLabel>
              <h3 className="mt-6 text-3xl tracking-tight transition-colors group-hover:text-[#3F6B2A] motion-reduce:transition-none">From report to resolution.</h3>
              <p className="mt-4 max-w-md leading-relaxed md:min-h-[4.5em]" style={{ color: INK_SOFT }}>Bring reports, policy checks, review, and signed documentation into one workflow. Your people stay in control of every decision.</p>
              <div className="my-7"><IncidentsPreview /></div>
              <span className="inline-flex items-center gap-3 text-sm font-medium">Explore Incident Reporting <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></span>
            </Link>
          </div>
        </section>

        <section className={`${WRAP} pb-20 sm:pb-28`} aria-labelledby="questions-title">
          <div className="grid gap-10 lg:grid-cols-12">
            <h2 id="questions-title" className="lg:col-span-5" style={{ ...display, fontSize: 'clamp(2.2rem, 4vw, 3.4rem)' }}>A few things<br />you might be asking.</h2>
            <div className="lg:col-span-7">
              {[
                ['Can we start with just one project?', 'Yes. Start with the challenge in front of you: a hiring process, a workflow that needs fixing, or a website. We’ll define a scope together and build from there if you need more.'],
                ['Do we need to use Matcha’s software?', 'We can help with your existing tools, build something custom, or work with Matcha’s software when it fits. The starting point is what your business needs.'],
                ['What is a closed AI system?', 'An AI system designed for a defined business use, with controlled access to your information and workflows. We work with you to define the data, permissions, and deployment approach for your needs.'],
              ].map(([question, answer]) => <details key={question} className="group border-t py-5" style={{ borderColor: hexA(INK, 0.16) }}><summary className="sched-focus flex cursor-pointer list-none items-center justify-between gap-5 rounded text-lg font-medium">{question}<span aria-hidden className="text-xl font-normal group-open:rotate-45 transition-transform motion-reduce:transition-none">+</span></summary><p className="mt-4 max-w-xl text-base leading-relaxed" style={{ color: INK_SOFT }}>{answer}</p></details>)}
            </div>
          </div>
        </section>

        <section className="sched-dark" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
          <div className={`${WRAP} border-b py-20 sm:py-24`} style={{ borderColor: hexA(PAPER, 0.15) }}>
            <Reveal className="grid gap-8 lg:grid-cols-12 lg:items-end">
              <div className="lg:col-span-8"><CellLabel n="04" dark>Let’s make room for what’s next</CellLabel><h2 className="mt-6 max-w-[16ch]" style={{ ...display, fontSize: 'clamp(2.8rem, 5.5vw, 5rem)' }}>What’s taking up<br />too much of your <Accent dark>day?</Accent></h2></div>
              <div className="lg:col-span-4"><p className="mb-7 max-w-sm text-lg leading-relaxed" style={{ color: hexA(PAPER, 0.68) }}>Bring us the challenge. We’ll work out the right next step together.</p><PrimaryButton tone="paper" onClick={onContact}>Talk to Matcha</PrimaryButton></div>
            </Reveal>
          </div>
        </section>
      </main>
    </>
  )
}
