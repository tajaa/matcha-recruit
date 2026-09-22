import { lazy, Suspense, useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useSEO } from '../../../hooks/useSEO'
import SchedulePlayer from './SchedulePlayer'
import {
  BODY,
  DISPLAY,
  FONT_HREF,
  HILITE,
  INK,
  INK_SOFT,
  MONO,
  PAPER,
  PAPER_DEEP,
  RED_PEN,
  STAMP,
  graphPaper,
  hexA,
} from './theme'
import { FORECAST_TOTAL, laborCost } from './weekData'

const PricingContactModal = lazy(() =>
  import('../../../components/marketing/PricingContactModal').then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
)

const CANONICAL = 'https://hey-matcha.com/matcha-scheduling'

const JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Matcha Scheduling',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  url: CANONICAL,
  description:
    'Shift scheduling for cafés, restaurants, and shops. Drafts the week from sales, weather, and availability, and checks overtime, rest, and qualifications before you publish.',
}

const WRAP = 'mx-auto w-full max-w-[1240px] px-4 sm:px-8'

const mono = (size: string, extra?: CSSProperties): CSSProperties => ({
  fontFamily: MONO,
  fontSize: size,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  ...extra,
})

const display: CSSProperties = {
  fontFamily: DISPLAY,
  fontWeight: 800,
  textTransform: 'uppercase',
  lineHeight: 0.9,
  letterSpacing: '-0.005em',
}

function useFonts() {
  useEffect(() => {
    if (document.querySelector(`link[href="${FONT_HREF}"]`)) return
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = FONT_HREF
    document.head.appendChild(link)
  }, [])
}

export default function SchedulingLanding() {
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useFonts()
  useSEO({
    title: 'Matcha Scheduling — Next week’s schedule, already written',
    description:
      'Shift scheduling for cafés, restaurants, and shops. Matcha drafts the week from your sales, the weather, and who can work, then checks overtime, rest, and availability before you publish.',
    canonical: CANONICAL,
    jsonLd: JSON_LD,
  })

  return (
    <div className="min-h-screen overflow-x-hidden" style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}>
      <LandingStyles />
      {contactMounted && (
        <Suspense fallback={null}>
          <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} mode="consultation" />
        </Suspense>
      )}

      <TopBar onContact={openContact} />
      <Hero onContact={openContact} />
      <main>
        <Inputs />
        <Rules />
        <AskInChat />
        <CostAndCrew />
        <Closing onContact={openContact} />
      </main>
      <Footer />
    </div>
  )
}

// ── chrome ────────────────────────────────────────────────────────────────

function PrimaryButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="sched-focus inline-flex h-12 items-center gap-2 rounded-full px-6 text-[15px] font-semibold transition-transform hover:-translate-y-0.5"
      style={{ backgroundColor: INK, color: PAPER }}
    >
      {children}
      <ArrowRight className="h-4 w-4" />
    </button>
  )
}

function TopBar({ onContact }: { onContact: () => void }) {
  return (
    <div className={`${WRAP} flex h-16 items-center justify-between sm:h-20`}>
      <Link to="/" className="sched-focus flex items-baseline gap-2 rounded" aria-label="Matcha home">
        <span style={{ fontFamily: DISPLAY, fontWeight: 900, fontSize: 26, letterSpacing: '0.01em' }}>MATCHA</span>
        <span style={mono('11px', { color: INK_SOFT })}>/ Scheduling</span>
      </Link>
      <nav className="flex items-center gap-5 sm:gap-7">
        <Link to="/login" className="sched-focus rounded text-[14px] font-medium hover:underline">
          Log in
        </Link>
        <button
          type="button"
          onClick={onContact}
          className="sched-focus hidden h-10 items-center rounded-full border px-4 text-[14px] font-semibold transition-colors hover:bg-[#18211B] hover:text-[#F2F4EF] sm:inline-flex"
          style={{ borderColor: INK }}
        >
          Book a walkthrough
        </button>
      </nav>
    </div>
  )
}

// ── hero ──────────────────────────────────────────────────────────────────

function Hero({ onContact }: { onContact: () => void }) {
  return (
    <header className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-0" style={{ ...graphPaper(24, 0.5), maskImage: 'linear-gradient(to bottom, black 55%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, black 55%, transparent)' }} />
      <div className={`${WRAP} relative pb-10 pt-10 sm:pt-16`}>
        <div style={mono('11.5px', { color: INK_SOFT })}>Shift scheduling for cafés, restaurants &amp; shops</div>
        <h1 className="mt-5" style={{ ...display, fontWeight: 900, fontSize: 'clamp(3.3rem, 10.5vw, 9.6rem)', lineHeight: 0.84 }}>
          Next week’s schedule,
          <br />
          <span className="sched-hilite">already written.</span>
        </h1>
        <div className="mt-8 grid gap-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <p className="max-w-[40rem] text-[1.1rem] leading-[1.55] sm:text-[1.25rem]" style={{ color: INK }}>
            Matcha drafts the week from your sales history, the weather, and who can actually work — then checks every shift for
            overtime, short turnarounds, and availability before you see it. You review, you publish.
          </p>
          <div className="flex flex-wrap items-center gap-5">
            <PrimaryButton onClick={onContact}>Book a walkthrough</PrimaryButton>
            <Link to="/login" className="sched-focus rounded text-[15px] font-medium underline-offset-4 hover:underline">
              Log in →
            </Link>
          </div>
        </div>

        <figure className="mt-12 sm:mt-16">
          <SchedulePlayer
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: INK_SOFT })}>Illustrative week · your draft is built from your own store’s data</span>
                <span className="flex flex-wrap gap-x-5 gap-y-2">
                  <Legend swatch={<span className="inline-block h-3 w-6 rounded-sm" style={{ backgroundColor: HILITE }} />} label="Shift" />
                  <Legend swatch={<span className="inline-block h-3 w-3 rounded-full border-2" style={{ borderColor: RED_PEN }} />} label="Flagged" />
                  <Legend swatch={<span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: STAMP }} />} label="Fixed · published" />
                </span>
              </div>
            }
          />
        </figure>
      </div>
    </header>
  )
}

function Legend({ swatch, label }: { swatch: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-2" style={mono('10.5px', { color: INK })}>
      {swatch}
      {label}
    </span>
  )
}

// ── what the draft reads ──────────────────────────────────────────────────

const INPUTS = [
  { tag: 'Sales', title: 'What you sold, by the hour', body: 'Committed sales from past weeks set how many people each part of the day needs.' },
  { tag: 'Weather', title: 'What the week will feel like', body: 'The forecast for your store’s address. A warm Saturday gets another person before the rush, not after it.' },
  { tag: 'Availability', title: 'Who said they can’t', body: 'Recurring availability, approved time off, and open requests. Nobody lands on a day they blocked.' },
  { tag: 'Jobs', title: 'Who can do the work', body: 'Shifts only go to people qualified for that job, with certifications that are current on the day.' },
]

function SectionHead({ kicker, title, children }: { kicker: string; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="max-w-3xl">
      <div style={mono('11px', { color: STAMP, fontWeight: 700 })}>{kicker}</div>
      <h2 className="mt-4" style={{ ...display, fontSize: 'clamp(2.4rem, 5.6vw, 4.4rem)' }}>
        {title}
      </h2>
      {children && (
        <p className="mt-5 max-w-2xl text-[1.05rem] leading-[1.6]" style={{ color: INK_SOFT }}>
          {children}
        </p>
      )}
    </div>
  )
}

function Inputs() {
  return (
    <section className={`${WRAP} py-20 sm:py-28`}>
      <SectionHead kicker="The draft" title="It starts from what you already know." />
      <div className="mt-12 grid gap-px overflow-hidden rounded-[6px] sm:grid-cols-2 lg:grid-cols-4" style={{ backgroundColor: hexA(INK, 0.18), border: `1px solid ${hexA(INK, 0.18)}` }}>
        {INPUTS.map((item) => (
          <div key={item.tag} className="flex flex-col p-6 sm:p-7" style={{ backgroundColor: PAPER }}>
            <span className="self-start rounded-sm px-1.5 py-0.5" style={mono('10.5px', { backgroundColor: HILITE, fontWeight: 700 })}>
              {item.tag}
            </span>
            <h3 className="mt-6 text-[1.3rem] font-semibold leading-tight">{item.title}</h3>
            <p className="mt-3 text-[0.98rem] leading-[1.55]" style={{ color: INK_SOFT }}>
              {item.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── the rules ─────────────────────────────────────────────────────────────

type Outcome = 'stops' | 'draft' | 'priced'

const RULES: { name: string; detail: string; outcome: Outcome }[] = [
  { name: 'Double-booking', detail: 'One person, two places at the same time.', outcome: 'stops' },
  { name: 'Outside availability', detail: 'A shift outside the hours someone set.', outcome: 'stops' },
  { name: 'Shift already full', detail: 'Headcount is met. Adding one more is your call.', outcome: 'stops' },
  { name: 'Short turnaround', detail: 'Less than 8 hours between a close and the next open.', outcome: 'draft' },
  { name: 'Weekly overtime', detail: 'Past 40 hours in the week — FLSA § 207(a).', outcome: 'draft' },
  { name: 'Minor hour limits', detail: 'Caps for crew under 18.', outcome: 'draft' },
  { name: 'Expired certifications', detail: 'A lapsed card or license on the day of the shift.', outcome: 'draft' },
  { name: 'California daily overtime', detail: 'Past 8 and 12 hours in a day — Cal. Lab. Code § 510.', outcome: 'priced' },
]

const OUTCOME: Record<Outcome, { label: string; style: CSSProperties }> = {
  stops: { label: 'Stops & asks you', style: { color: RED_PEN, border: `1.5px solid ${RED_PEN}` } },
  draft: { label: 'Fixed in the draft', style: { backgroundColor: HILITE, color: INK, border: `1.5px solid ${HILITE}` } },
  priced: { label: 'Priced in', style: { color: STAMP, border: `1.5px solid ${STAMP}` } },
}

function Rules() {
  return (
    <section style={{ backgroundColor: PAPER_DEEP }}>
      <div className={`${WRAP} py-20 sm:py-28`}>
        <SectionHead kicker="The check" title={<>Checked before it<br className="hidden sm:block" /> reaches you.</>}>
          The draft is built around these, so you start from a week that already works. The hard ones — double-booking,
          availability, a full shift — also stop a manual edit until you confirm it on purpose.
        </SectionHead>
        <ul className="mt-12">
          {RULES.map((rule) => (
            <li
              key={rule.name}
              className="grid gap-2 py-5 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1.5fr)_11rem] sm:items-center sm:gap-6"
              style={{ borderTop: `1px solid ${hexA(INK, 0.22)}` }}
            >
              <span style={{ ...display, fontSize: 'clamp(1.6rem, 2.6vw, 2.1rem)', fontWeight: 800 }}>{rule.name}</span>
              <span className="text-[1rem] leading-[1.5]" style={{ color: INK_SOFT }}>
                {rule.detail}
              </span>
              <span className="justify-self-start rounded-full px-3 py-1 sm:justify-self-end" style={mono('10.5px', { fontWeight: 700, ...OUTCOME[rule.outcome].style })}>
                {OUTCOME[rule.outcome].label}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

// ── chat edits ────────────────────────────────────────────────────────────

function AskInChat() {
  return (
    <section className={`${WRAP} grid gap-12 py-20 sm:py-28 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center lg:gap-20`}>
      <SectionHead kicker="Changes" title="Change it in a sentence.">
        Type it the way you’d tell a shift lead. Huume drafts the edit, shows who moves and what it does to their hours, and waits
        for you to confirm. Nothing changes until you do.
      </SectionHead>

      <div className="rounded-[10px] p-4 sm:p-6" style={{ backgroundColor: '#fff', border: `1.5px solid ${INK}`, boxShadow: `8px 8px 0 ${hexA(INK, 0.9)}` }}>
        <div className="flex items-center justify-between pb-3" style={{ borderBottom: `1px solid ${hexA(INK, 0.12)}` }}>
          <span style={mono('10.5px', { color: INK_SOFT })}># mission-st</span>
          <span style={mono('10.5px', { color: INK_SOFT })}>Sun 3:58 PM</span>
        </div>
        <div className="mt-4 flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-sm px-4 py-2.5 text-[15px]" style={{ backgroundColor: INK, color: PAPER }}>
            <span style={{ color: HILITE, fontWeight: 600 }}>@huume</span> give Dev’s Tuesday open to Jonah
          </div>
        </div>
        <div className="mt-4 rounded-lg p-4" style={{ backgroundColor: PAPER, border: `1px solid ${hexA(INK, 0.16)}` }}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span style={mono('10.5px', { color: STAMP, fontWeight: 700 })}>Proposed · reassign</span>
            <span style={mono('10.5px', { color: INK_SOFT })}>Tue Oct 6 · 7a–3p · Barista</span>
          </div>
          <div className="mt-3 text-[1.05rem] font-semibold">Dev P. → Jonah B.</div>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[14px]">
            <dt style={{ color: INK_SOFT }}>Jonah</dt>
            <dd style={{ fontFamily: MONO }}>32h → 40h · no overtime</dd>
            <dt style={{ color: INK_SOFT }}>Dev</dt>
            <dd style={{ fontFamily: MONO }}>32h → 24h</dd>
            <dt style={{ color: INK_SOFT }}>Checks</dt>
            <dd style={{ fontFamily: MONO, color: STAMP }}>available · qualified · 8h+ rest</dd>
          </dl>
          <div className="mt-4 flex gap-2">
            <span className="inline-flex h-9 items-center rounded-full px-4 text-[14px] font-semibold" style={{ backgroundColor: STAMP, color: PAPER }}>
              Confirm
            </span>
            <span className="inline-flex h-9 items-center rounded-full px-4 text-[14px] font-medium" style={{ border: `1px solid ${hexA(INK, 0.3)}` }}>
              Cancel
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── cost + crew ───────────────────────────────────────────────────────────

const REQUESTS = [
  { kind: 'Swap', what: 'Sat close', who: 'Priya ↔ Theo' },
  { kind: 'Time off', what: 'Oct 14–16', who: 'Kiko' },
  { kind: 'Availability', what: 'No Tuesdays from Nov 1', who: 'Sam' },
]

function CostAndCrew() {
  const cost = laborCost(true)
  const pct = ((cost.total / FORECAST_TOTAL) * 100).toFixed(1)
  return (
    <section style={{ borderTop: `1.5px solid ${INK}`, borderBottom: `1.5px solid ${INK}` }}>
      <div className={`${WRAP} grid lg:grid-cols-2`}>
        <div className="py-16 sm:py-20 lg:pr-14" style={{ borderColor: INK }}>
          <div style={mono('11px', { color: STAMP, fontWeight: 700 })}>Cost</div>
          <h2 className="mt-4" style={{ ...display, fontSize: 'clamp(2.1rem, 4vw, 3.2rem)' }}>
            Know what the week costs before it’s posted.
          </h2>
          <div className="mt-8 flex flex-wrap items-end gap-x-8 gap-y-3">
            <div style={{ fontFamily: DISPLAY, fontWeight: 900, fontSize: 'clamp(4rem, 9vw, 6.5rem)', lineHeight: 0.85 }}>
              ${Math.round(cost.total).toLocaleString('en-US')}
            </div>
            <div style={mono('11px', { color: INK_SOFT, lineHeight: 1.7 })}>
              scheduled labor
              <br />
              {pct}% of forecast sales
              <br />
              $0 overtime
            </div>
          </div>
          <p className="mt-8 max-w-lg text-[1rem] leading-[1.6]" style={{ color: INK_SOFT }}>
            Every shift is priced from the pay rate on file, with weekly and California daily overtime applied. Anyone without a
            rate shows as <span style={{ color: INK, fontWeight: 600 }}>unpriced</span> — never as $0.
          </p>
        </div>

        <div className="py-16 sm:py-20 lg:border-l lg:pl-14" style={{ borderColor: INK, borderTopWidth: 0 }}>
          <div style={mono('11px', { color: STAMP, fontWeight: 700 })}>Crew</div>
          <h2 className="mt-4" style={{ ...display, fontSize: 'clamp(2.1rem, 4vw, 3.2rem)' }}>
            Your crew asks from their phone.
          </h2>
          <p className="mt-5 max-w-lg text-[1rem] leading-[1.6]" style={{ color: INK_SOFT }}>
            Published shifts show up in their portal. Swaps, drops, time off, and availability changes come to you as requests.
            Approve one and the schedule updates; deny it and nothing moves.
          </p>
          <ul className="mt-8 space-y-2">
            {REQUESTS.map((r) => (
              <li key={r.kind} className="flex items-center justify-between gap-3 rounded-lg px-4 py-3" style={{ backgroundColor: '#fff', border: `1px solid ${hexA(INK, 0.16)}` }}>
                <span className="min-w-0">
                  <span style={mono('10px', { color: INK_SOFT })}>{r.kind}</span>
                  <span className="block truncate text-[15px] font-medium">
                    {r.who} · {r.what}
                  </span>
                </span>
                <span className="shrink-0 rounded-full px-3 py-1 text-[13px] font-semibold" style={{ border: `1.5px solid ${STAMP}`, color: STAMP }}>
                  Approve
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

// ── close ─────────────────────────────────────────────────────────────────

function Closing({ onContact }: { onContact: () => void }) {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0" style={graphPaper(24, 0.45)} />
      <div className={`${WRAP} relative py-24 sm:py-32`}>
        <h2 style={{ ...display, fontWeight: 900, fontSize: 'clamp(3rem, 9vw, 8rem)', lineHeight: 0.86 }}>
          Take Sunday night <span className="sched-hilite sched-hilite-static">back.</span>
        </h2>
        <div className="mt-10 flex flex-wrap items-center gap-6">
          <PrimaryButton onClick={onContact}>Book a walkthrough</PrimaryButton>
          <p className="max-w-md text-[0.98rem] leading-[1.55]" style={{ color: INK_SOFT }}>
            Scheduling is part of{' '}
            <Link to="/matcha-ops" className="sched-focus rounded font-medium underline underline-offset-4" style={{ color: INK }}>
              Matcha Ops
            </Link>{' '}
            — events, inventory, and team channels for every location, in the same place.
          </p>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer style={{ backgroundColor: INK, color: PAPER }}>
      <div className={`${WRAP} flex flex-col gap-4 py-8 sm:flex-row sm:items-center sm:justify-between`}>
        <span style={{ fontFamily: DISPLAY, fontWeight: 900, fontSize: 22 }}>MATCHA</span>
        <nav className="flex flex-wrap gap-x-6 gap-y-2" style={mono('10.5px')}>
          <Link className="sched-focus rounded hover:underline" to="/">hey-matcha.com</Link>
          <Link className="sched-focus rounded hover:underline" to="/privacy">Privacy</Link>
          <Link className="sched-focus rounded hover:underline" to="/terms">Terms</Link>
          <span style={{ opacity: 0.6 }}>© {new Date().getFullYear()} Matcha</span>
        </nav>
      </div>
    </footer>
  )
}

function LandingStyles() {
  return (
    <style>{`
      .sched-hilite {
        background-image: linear-gradient(${HILITE}, ${HILITE});
        background-repeat: no-repeat;
        background-position: 0 88%;
        background-size: 100% 62%;
        padding: 0 0.06em;
        margin: 0 -0.06em;
        -webkit-box-decoration-break: clone;
        box-decoration-break: clone;
        animation: schedSwipe 900ms cubic-bezier(.2,.7,.2,1) 250ms both;
      }
      .sched-hilite-static { animation: none; }
      @keyframes schedSwipe { from { background-size: 0% 62%; } to { background-size: 100% 62%; } }
      .sched-focus:focus-visible { outline: 2px solid ${INK}; outline-offset: 3px; }
      footer .sched-focus:focus-visible { outline-color: ${PAPER}; }
      .sched-sheet { box-shadow: 0 1px 0 ${hexA(INK, 0.08)}, 0 30px 60px -30px ${hexA(INK, 0.35)}; }
      @media (prefers-reduced-motion: reduce) {
        .sched-hilite { animation: none; }
      }
    `}</style>
  )
}
