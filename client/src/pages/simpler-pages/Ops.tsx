import { lazy, Suspense, useState, type CSSProperties } from 'react'
import { ArrowRight, CalendarDays, ClipboardList, Hash, Package, Radio, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, LEAF, LINE_D, NOIR, ASH, SURFACE } from '../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../home/layout'
import { GrainOverlay, PageStyle, Reveal, useMarketingNoir } from '../home/PageChrome'

const PricingContactModal = lazy(() =>
  import('../../components/marketing/PricingContactModal').then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
)

const OPS_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Matcha Ops',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  description: 'The operational layer for events, inventory, scheduling, and company channels.',
}

const CAPABILITIES = [
  {
    icon: ClipboardList,
    index: '01',
    title: 'Events',
    description: 'Capture what happened while the details are still fresh, then turn the record into a shared operational signal.',
  },
  {
    icon: Package,
    index: '02',
    title: 'Inventory',
    description: 'Track stock, movements, and orders in the same workspace where your team is already coordinating.',
  },
  {
    icon: CalendarDays,
    index: '03',
    title: 'Schedule',
    description: 'Plan shifts, manage requests, and keep coverage visible before a gap becomes an interruption.',
  },
  {
    icon: Hash,
    index: '04',
    title: 'Channels',
    description: 'Give every location and operating group a live place to coordinate decisions, context, and follow-through.',
  },
] as const

const SIGNALS = [
  { label: 'Event logged', value: '09:42', color: LEAF },
  { label: 'Stock movement', value: '12 units', color: '#D6A15A' },
  { label: 'Coverage confirmed', value: '100%', color: '#8FB6D9' },
]

const FLOATING_CARD_STYLE: CSSProperties = {
  transformStyle: 'preserve-3d',
  boxShadow: '0 28px 60px rgba(0, 0, 0, 0.35), 0 2px 5px rgba(0, 0, 0, 0.25)',
}

export default function MatchaOpsPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false)

  const openPricing = () => {
    setHasOpenedPricing(true)
    setIsPricingOpen(true)
  }

  useMarketingNoir()

  useSEO({
    title: 'Matcha Ops — The Operational Layer for Modern Teams',
    description:
      'Events, inventory, scheduling, and company channels in one operational layer built for teams that need the whole picture in motion.',
    canonical: 'https://hey-matcha.com/matcha-ops',
    jsonLd: OPS_JSON_LD,
  })

  return (
    <div style={{ backgroundColor: NOIR, color: BONE }} className="home-root min-h-screen overflow-x-hidden">
      <PageStyle />
      <GrainOverlay />

      {hasOpenedPricing && (
        <Suspense
          fallback={
            isPricingOpen ? (
              <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-t-white/90" role="status" aria-label="Loading" />
              </div>
            ) : null
          }
        >
          <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
        </Suspense>
      )}

      <MarketingNav onDemoClick={openPricing} transparentAtTop />

      <Hero onContactClick={openPricing} />

      <main>
        <Capabilities />
        <SignalSection />
        <ClosingCta onContactClick={openPricing} />
      </main>

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}

function Hero({ onContactClick }: { onContactClick: () => void }) {
  return (
    <header className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute -left-[15%] top-0 h-[620px] w-[65%]"
        style={{ background: 'radial-gradient(ellipse, rgba(163,197,125,0.10), transparent 68%)' }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-[20%] top-[18%] h-[520px] w-[60%]"
        style={{ background: 'radial-gradient(ellipse, rgba(94,125,167,0.10), transparent 68%)' }}
      />

      <div className={`${CONTAINER} relative grid min-h-[720px] items-center gap-12 pb-20 pt-32 lg:grid-cols-[0.9fr_1.1fr] lg:gap-6 lg:pb-16 lg:pt-28`}>
        <div className="relative z-10 max-w-xl">
          <div className="home-fade-fast mb-7 inline-flex items-center gap-2 rounded-full border px-3 py-1.5" style={{ borderColor: LINE_D, color: ASH }}>
            <span className="h-1.5 w-1.5 rounded-full home-pulse" style={{ backgroundColor: LEAF }} />
            <span className={`${EYEBROW} !tracking-[0.18em]`}>The operational layer</span>
          </div>
          <h1 className="tracking-[-0.045em] text-[clamp(3rem,6.6vw,6.8rem)]" style={{ fontFamily: 'var(--font-lite)', fontWeight: 300, lineHeight: 0.95 }}>
            Keep the whole <span style={{ color: LEAF, fontStyle: 'italic' }}>operation</span> in view.
          </h1>
          <p className="home-fade-fast mt-7 max-w-lg text-[1.05rem] leading-[1.5] sm:text-[1.2rem]" style={{ animationDelay: '100ms', color: ASH, fontFamily: 'var(--font-lite)', fontWeight: 300 }}>
            Matcha Ops connects events, inventory, scheduling, and team channels so the work between the plan and the outcome stays visible.
          </p>
          <div className="home-fade-fast mt-9 flex flex-wrap items-center gap-4" style={{ animationDelay: '180ms' }}>
            <button type="button" onClick={onContactClick} className="inline-flex h-12 items-center justify-center gap-2 rounded-full px-6 text-[15px] font-medium transition-opacity hover:opacity-90" style={{ backgroundColor: LEAF, color: '#14210B' }}>
              See Matcha Ops
              <ArrowRight className="h-4 w-4" />
            </button>
            <Link to="/login" className="inline-flex h-12 items-center text-[15px] transition-opacity hover:opacity-60" style={{ color: BONE }}>
              Client login →
            </Link>
          </div>
        </div>

        <OpsConsole />
      </div>
    </header>
  )
}

function OpsConsole() {
  return (
    <div className="relative mx-auto w-full max-w-[650px] overflow-visible" style={{ perspective: '1300px' }}>
      <div aria-hidden className="absolute left-[18%] top-[15%] h-[65%] w-[65%] rounded-full blur-3xl" style={{ backgroundColor: 'rgba(163,197,125,0.12)' }} />

      <div className="relative mx-auto aspect-[1.04] w-[86%] rounded-[26px] border p-3 sm:p-4" style={{ ...FLOATING_CARD_STYLE, transform: 'rotateX(8deg) rotateY(-13deg) rotateZ(1deg)', background: 'linear-gradient(145deg, rgba(35,42,34,0.94), rgba(14,18,15,0.98))', borderColor: 'rgba(188,216,151,0.24)' }}>
        <div className="h-full rounded-[18px] border p-4 sm:p-6" style={{ background: 'linear-gradient(145deg, rgba(245,242,237,0.08), rgba(245,242,237,0.025))', borderColor: 'rgba(245,242,237,0.12)', transform: 'translateZ(28px)' }}>
          <div className="flex items-center justify-between border-b pb-4" style={{ borderColor: 'rgba(245,242,237,0.10)' }}>
            <div className="flex items-center gap-2">
              <Radio size={14} style={{ color: LEAF }} />
              <span className="font-mk-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: ASH }}>Matcha Ops / Live</span>
            </div>
            <span className="rounded-full px-2 py-1 text-[9px] font-mk-mono uppercase tracking-wider" style={{ backgroundColor: 'rgba(163,197,125,0.12)', color: LEAF }}>Synced</span>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-2 sm:gap-3">
            {[
              ['Signals', '24'],
              ['Coverage', '100%'],
              ['Open work', '08'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border p-3" style={{ backgroundColor: 'rgba(0,0,0,0.16)', borderColor: 'rgba(245,242,237,0.08)' }}>
                <div className="font-mk-mono text-[9px] uppercase tracking-wider" style={{ color: ASH }}>{label}</div>
                <div className="mt-2 text-xl tracking-tight sm:text-2xl" style={{ color: BONE, fontFamily: 'var(--font-lite)' }}>{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border p-3 sm:p-4" style={{ backgroundColor: 'rgba(0,0,0,0.18)', borderColor: 'rgba(245,242,237,0.08)' }}>
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mk-mono text-[9px] uppercase tracking-wider" style={{ color: ASH }}>Operational pulse</span>
              <span className="text-[10px]" style={{ color: LEAF }}>Today</span>
            </div>
            <div className="flex h-24 items-end gap-1.5 sm:h-28 sm:gap-2">
              {[32, 48, 38, 64, 53, 72, 58, 84, 69, 92, 76, 88].map((height, index) => (
                <div key={index} className="flex-1 rounded-t-sm" style={{ height: `${height}%`, background: index > 8 ? 'linear-gradient(to top, #668C4F, #BCD897)' : 'rgba(163,197,125,0.32)' }} />
              ))}
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {SIGNALS.map((signal) => (
              <div key={signal.label} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ backgroundColor: 'rgba(245,242,237,0.045)' }}>
                <span className="flex items-center gap-2 text-[11px]" style={{ color: ASH }}><span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: signal.color }} />{signal.label}</span>
                <span className="font-mk-mono text-[10px]" style={{ color: BONE }}>{signal.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="absolute -left-1 top-[12%] hidden rounded-2xl border p-3 sm:block sm:-left-4" style={{ ...FLOATING_CARD_STYLE, transform: 'translateZ(90px) rotateY(10deg) rotateZ(-4deg)', backgroundColor: 'rgba(23,27,22,0.92)', borderColor: 'rgba(163,197,125,0.28)' }}>
        <div className="flex items-center gap-2"><ClipboardList size={13} style={{ color: LEAF }} /><span className="text-[10px]" style={{ color: BONE }}>Event logged</span></div>
        <div className="mt-2 font-mk-mono text-[9px]" style={{ color: ASH }}>Store 04 · 09:42</div>
      </div>

      <div className="absolute -right-1 bottom-[17%] hidden rounded-2xl border p-3 sm:block sm:-right-5" style={{ ...FLOATING_CARD_STYLE, transform: 'translateZ(110px) rotateY(-12deg) rotateZ(4deg)', backgroundColor: 'rgba(23,27,22,0.94)', borderColor: 'rgba(143,182,217,0.25)' }}>
        <div className="flex items-center gap-2"><ShieldCheck size={13} style={{ color: '#8FB6D9' }} /><span className="text-[10px]" style={{ color: BONE }}>Coverage clear</span></div>
        <div className="mt-2 font-mk-mono text-[9px]" style={{ color: ASH }}>Next shift · 06:00</div>
      </div>
    </div>
  )
}

function Capabilities() {
  return (
    <section className={`${CONTAINER} ${SECTION_Y}`}>
      <Reveal>
        <div className="grid gap-8 lg:grid-cols-[0.7fr_1.3fr] lg:gap-20">
          <div>
            <div className={EYEBROW} style={{ color: LEAF }}>One operating picture</div>
            <h2 className="mt-5 max-w-md text-4xl tracking-[-0.035em] sm:text-5xl" style={{ fontFamily: 'var(--font-lite)', fontWeight: 300, lineHeight: 1.02 }}>The details that keep a day moving.</h2>
          </div>
          <p className="max-w-xl self-end text-lg leading-[1.55]" style={{ color: ASH, fontFamily: 'var(--font-lite)', fontWeight: 300 }}>The front line should not have to reconstruct the day from scattered tools. Matcha Ops gives the people doing the work a clear place to log, coordinate, and close the loop.</p>
        </div>
      </Reveal>

      <div className="mt-16 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {CAPABILITIES.map((capability, index) => {
          const Icon = capability.icon
          return (
            <Reveal key={capability.title} delayMs={index * 70}>
              <div className="group h-full rounded-2xl border p-5 transition-transform duration-300 hover:-translate-y-1" style={{ backgroundColor: SURFACE, borderColor: LINE_D }}>
                <div className="flex items-start justify-between"><Icon size={19} style={{ color: LEAF }} /><span className="font-mk-mono text-[10px]" style={{ color: ASH }}>{capability.index}</span></div>
                <h3 className="mt-12 text-lg" style={{ fontFamily: 'var(--font-lite)', color: BONE }}>{capability.title}</h3>
                <p className="mt-2 text-sm leading-6" style={{ color: ASH }}>{capability.description}</p>
              </div>
            </Reveal>
          )
        })}
      </div>
    </section>
  )
}

function SignalSection() {
  return (
    <section className="border-y" style={{ borderColor: LINE_D, backgroundColor: 'rgba(245,242,237,0.025)' }}>
      <div className={`${CONTAINER} ${SECTION_Y}`}>
        <Reveal>
          <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-24">
            <div>
              <div className={EYEBROW} style={{ color: '#D6A15A' }}>Built for motion</div>
              <h2 className="mt-5 max-w-lg text-4xl tracking-[-0.035em] sm:text-5xl" style={{ fontFamily: 'var(--font-lite)', fontWeight: 300, lineHeight: 1.02 }}>Less chasing. More knowing.</h2>
              <p className="mt-6 max-w-md text-base leading-7" style={{ color: ASH }}>Every update has a home, every handoff has context, and every manager can see what needs attention before the next shift starts.</p>
            </div>
            <div className="relative rounded-3xl border p-3 sm:p-5" style={{ borderColor: LINE_D, background: 'linear-gradient(135deg, rgba(245,242,237,0.08), rgba(245,242,237,0.018))', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 30px 80px rgba(0,0,0,0.18)' }}>
              <div className="rounded-2xl border p-5 sm:p-7" style={{ borderColor: 'rgba(245,242,237,0.09)', backgroundColor: 'rgba(14,14,12,0.72)' }}>
                <div className="flex items-center justify-between"><span className="font-mk-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: ASH }}>The operating loop</span><Hash size={15} style={{ color: LEAF }} /></div>
                <div className="mt-8 space-y-0">
                  {['Capture the signal', 'Coordinate the response', 'Close the loop'].map((step, index) => (
                    <div key={step} className="relative flex gap-4 pb-8 last:pb-0">
                      {index < 2 && <span className="absolute left-[11px] top-7 h-full w-px" style={{ backgroundColor: 'rgba(163,197,125,0.22)' }} />}
                      <span className="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-mk-mono" style={{ borderColor: 'rgba(163,197,125,0.45)', backgroundColor: '#182116', color: LEAF }}>{String(index + 1).padStart(2, '0')}</span>
                      <div><div className="text-base" style={{ color: BONE }}>{step}</div><div className="mt-1 text-sm" style={{ color: ASH }}>{['Events and updates land where the team can act.', 'The right people have the context to move.', 'The record stays useful after the moment passes.'][index]}</div></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function ClosingCta({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className={`${CONTAINER} py-28 sm:py-36 md:py-44`}>
      <Reveal>
        <div className="relative overflow-hidden rounded-3xl border px-6 py-14 text-center sm:px-12 sm:py-20" style={{ borderColor: 'rgba(163,197,125,0.26)', background: 'radial-gradient(circle at 50% 0%, rgba(163,197,125,0.14), transparent 58%), rgba(245,242,237,0.035)' }}>
          <div className={EYEBROW} style={{ color: LEAF }}>Make the operation legible</div>
          <h2 className="mx-auto mt-5 max-w-2xl text-4xl tracking-[-0.035em] sm:text-6xl" style={{ fontFamily: 'var(--font-lite)', fontWeight: 300, lineHeight: 1 }}>The next shift starts with a clearer picture.</h2>
          <button type="button" onClick={onContactClick} className="mt-9 inline-flex h-12 items-center gap-2 rounded-full px-6 text-[15px] font-medium transition-opacity hover:opacity-90" style={{ backgroundColor: LEAF, color: '#14210B' }}>Talk to us about Matcha Ops <ArrowRight size={16} /></button>
        </div>
      </Reveal>
    </section>
  )
}
