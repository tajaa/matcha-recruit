import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingBag, CalendarClock, Mail, ClipboardList, PenLine, BarChart3 } from 'lucide-react'

// Gummfit landing — dark, type-led, one electric accent. Fraunces (display) +
// Roboto Flex (body) are loaded globally; visuals are pure CSS (no imagery).
const BG = '#0A0A09'
const INK = '#F4F1E8'
const MUTED = '#8E8B81'
const LINE = 'rgba(244,241,232,0.10)'
const ACCENT = '#C6F16B'
const ACCENT_DIM = 'rgba(198,241,107,0.14)'
const DISPLAY = 'var(--font-display)'
const WRAP = 'max-w-[1400px] mx-auto px-6 sm:px-10'

const SELLS = ['your products.', 'your downloads.', 'your sessions.', 'your reports.', 'your time.', 'your craft.']
const PERSONAS = ['Photographers', 'Chefs', 'Consultants', 'Trainers', 'Studios', 'Nutritionists', 'Designers', 'Coaches', 'Tutors', 'Florists', 'Makers']

const OFFERINGS = [
  { n: '01', t: 'Goods', d: 'Physical products you ship, with real inventory.' },
  { n: '02', t: 'Downloads', d: 'A file they receive the instant they pay.' },
  { n: '03', t: 'Services', d: 'Work you deliver — a report, a package — and mark done.' },
  { n: '04', t: 'Bookings', d: 'Open time on your calendar, theirs to reserve.' },
]

const FEATURES = [
  { icon: ShoppingBag, t: 'Storefront', d: 'Goods, downloads and services on one page, priced and ready to buy. Checkout included.' },
  { icon: CalendarClock, t: 'Bookings', d: 'Publish your availability. Clients pick a slot and pay for it in the same motion.' },
  { icon: Mail, t: 'Campaigns', d: 'Collect subscribers on your site, then write to all of them at once. No third-party list tool.' },
  { icon: ClipboardList, t: 'Forms', d: 'Intake, inquiries, quotes — build the form, answers land in your dashboard.' },
  { icon: PenLine, t: 'Blog', d: 'A clean writing surface under your own name. Posts live on your site, not a platform.' },
  { icon: BarChart3, t: 'Orders', d: 'Every sale, booking and download in one ledger. Mark work delivered, watch revenue add up.' },
]

const STEPS = [
  { n: 'i', t: 'Choose a template', d: 'Start from a designed, editable site.' },
  { n: 'ii', t: 'Make it yours', d: 'Edit every block live. Add your work and your prices.' },
  { n: 'iii', t: 'Publish & get paid', d: 'Go live on your own address — they buy right there.' },
]

/** Cross-fades through a list of words in place. */
function Cycle({ words }: { words: string[] }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % words.length), 2300)
    return () => clearInterval(t)
  }, [words.length])
  return (
    <span key={i} className="italic" style={{ color: ACCENT, animation: 'gfWord .6s cubic-bezier(.2,.7,.2,1) both', display: 'inline-block' }}>
      {words[i]}
    </span>
  )
}

/** Reveals children on scroll-in. */
function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect() } }, { threshold: 0.18 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={ref} style={{ transitionDelay: `${delay}ms` }}
      className={`transition-[opacity,transform] duration-[900ms] ease-[cubic-bezier(.2,.7,.2,1)] ${shown ? 'translate-y-0 opacity-100' : 'translate-y-6 opacity-0'} ${className}`}>
      {children}
    </div>
  )
}

/** Pure-CSS browser-window mock of a Gummfit site — no imagery needed. */
function SiteMock() {
  return (
    <div className="mx-auto mt-16 w-full max-w-3xl" style={{ animation: 'gfFloat 7s ease-in-out infinite' }}>
      <div className="overflow-hidden rounded-2xl border shadow-[0_40px_120px_-30px_rgba(198,241,107,0.18)]"
        style={{ borderColor: LINE, background: 'linear-gradient(180deg, rgba(244,241,232,0.04), rgba(244,241,232,0.01))', backdropFilter: 'blur(8px)' }}>
        {/* chrome */}
        <div className="flex items-center gap-2 border-b px-4 py-3" style={{ borderColor: LINE }}>
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgba(244,241,232,0.18)' }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgba(244,241,232,0.18)' }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgba(244,241,232,0.18)' }} />
          <span className="mx-auto rounded-full border px-4 py-1 text-[11px] tracking-wide" style={{ borderColor: LINE, color: MUTED }}>
            <span style={{ color: ACCENT }}>yourname</span>.gummfit.com
          </span>
          <span className="w-12" />
        </div>
        {/* page */}
        <div className="px-7 py-8 sm:px-10">
          <div className="flex items-center justify-between">
            <div className="h-3 w-24 rounded-full" style={{ background: 'rgba(244,241,232,0.25)' }} />
            <div className="flex gap-2">
              <div className="h-3 w-12 rounded-full" style={{ background: 'rgba(244,241,232,0.12)' }} />
              <div className="h-3 w-12 rounded-full" style={{ background: 'rgba(244,241,232,0.12)' }} />
              <div className="h-3 w-14 rounded-full" style={{ background: ACCENT_DIM }} />
            </div>
          </div>
          <div className="mt-9 h-6 w-3/5 rounded-md" style={{ background: 'rgba(244,241,232,0.22)' }} />
          <div className="mt-3 h-6 w-2/5 rounded-md" style={{ background: 'rgba(244,241,232,0.12)' }} />
          <div className="mt-8 grid grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-xl border p-4" style={{ borderColor: LINE, background: 'rgba(244,241,232,0.025)' }}>
                <div className="h-16 rounded-lg sm:h-20"
                  style={{ background: i === 1 ? 'linear-gradient(135deg, rgba(198,241,107,0.35), rgba(198,241,107,0.08))' : 'rgba(244,241,232,0.07)' }} />
                <div className="mt-3 h-2.5 w-3/4 rounded-full" style={{ background: 'rgba(244,241,232,0.18)' }} />
                <div className="mt-2 flex items-center justify-between">
                  <div className="h-2.5 w-10 rounded-full" style={{ background: 'rgba(244,241,232,0.10)' }} />
                  <div className="h-5 w-14 rounded-full" style={{ background: ACCENT_DIM, border: `1px solid rgba(198,241,107,0.35)` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function CappeLanding() {
  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <style>{`
        @keyframes gfRise{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
        .gf-rise{animation:gfRise 1s cubic-bezier(.2,.7,.2,1) both}
        @keyframes gfWord{from{opacity:0;transform:translateY(.45em)}to{opacity:1;transform:none}}
        @keyframes gfMarquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
        .gf-marquee{animation:gfMarquee 38s linear infinite}
        .gf-marquee:hover{animation-play-state:paused}
        @keyframes gfGlow{0%,100%{opacity:.5;transform:translate(-50%,0) scale(1)}50%{opacity:.85;transform:translate(-50%,-4%) scale(1.08)}}
        @keyframes gfFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
        .gf-card{transition:transform .5s cubic-bezier(.2,.7,.2,1), border-color .5s, background .5s}
        .gf-card:hover{transform:translateY(-4px);border-color:rgba(198,241,107,0.4);background:rgba(198,241,107,0.05)}
        .gf-grid-bg{background-image:linear-gradient(rgba(244,241,232,0.035) 1px, transparent 1px),linear-gradient(90deg, rgba(244,241,232,0.035) 1px, transparent 1px);background-size:56px 56px;mask-image:radial-gradient(ellipse 80% 60% at 50% 0%, black, transparent)}
      `}</style>

      {/* nav */}
      <header className={`relative z-20 flex items-center justify-between py-7 ${WRAP}`}>
        <span style={{ fontFamily: DISPLAY }} className="text-2xl font-semibold tracking-tight">
          Gummfit<span style={{ color: ACCENT }}>.</span>
        </span>
        <div className="flex items-center gap-7 text-sm">
          <Link to="/cappe/templates" className="hidden transition-colors hover:text-white sm:block" style={{ color: MUTED }}>Templates</Link>
          <Link to="/cappe/login" className="transition-colors hover:text-white" style={{ color: MUTED }}>Sign in</Link>
          <Link to="/cappe/website-setup" className="rounded-full px-5 py-2.5 font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
            Start building
          </Link>
        </div>
      </header>

      {/* hero */}
      <section className="relative isolate">
        <div className="gf-grid-bg pointer-events-none absolute inset-0 -z-20" />
        <div className="pointer-events-none absolute left-1/2 top-[-14%] -z-10 h-[44rem] w-[60rem] rounded-full blur-[140px]"
          style={{ background: 'radial-gradient(closest-side, rgba(150,200,70,0.20), transparent)', animation: 'gfGlow 9s ease-in-out infinite' }} />
        <div className={`${WRAP} pb-24 pt-14 text-center sm:pb-28 sm:pt-20`}>
          <p className="gf-rise inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-[11px] uppercase tracking-[0.3em]"
            style={{ color: ACCENT, borderColor: 'rgba(198,241,107,0.3)', background: 'rgba(198,241,107,0.06)' }}>
            Website builder + storefront
          </p>
          <h1 className="gf-rise mx-auto mt-8 max-w-[18ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.9rem,8.5vw,7rem)', lineHeight: 0.95, animationDelay: '90ms' }}>
            A website that sells{' '}
            <span className="block sm:inline"><Cycle words={SELLS} /></span>
          </h1>
          <p className="gf-rise mx-auto mt-8 max-w-xl text-lg leading-relaxed" style={{ color: MUTED, animationDelay: '180ms' }}>
            Gummfit turns your craft into a site and a storefront — products, downloads, services and
            bookings, plus the newsletter, forms and blog to grow it. You set the price. No code, no plugins.
          </p>
          <div className="gf-rise mt-11 flex items-center justify-center gap-6" style={{ animationDelay: '260ms' }}>
            <Link to="/cappe/website-setup" className="inline-flex h-12 items-center rounded-full px-7 text-[15px] font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
              Start building — it’s free
            </Link>
            <Link to="/cappe/templates" className="inline-flex h-12 items-center text-[15px] transition-colors hover:text-white" style={{ color: MUTED }}>
              See templates →
            </Link>
          </div>
          <SiteMock />
        </div>
      </section>

      {/* kinetic persona marquee */}
      <div className="relative flex overflow-hidden border-y py-7" style={{ borderColor: LINE }}>
        <div className="gf-marquee flex shrink-0 whitespace-nowrap">
          {[...PERSONAS, ...PERSONAS].map((p, i) => (
            <span key={i} style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(1.4rem,3.4vw,2.6rem)' }} className="mx-7">
              <span style={{ color: i % 4 === 0 ? ACCENT : MUTED }}>{p}</span>
              <span className="mx-7" style={{ color: 'rgba(244,241,232,0.22)' }}>/</span>
            </span>
          ))}
        </div>
      </div>

      {/* everything included — feature grid */}
      <section className="border-b py-28 sm:py-36" style={{ borderColor: LINE }}>
        <div className={WRAP}>
          <Reveal>
            <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.3em]" style={{ color: ACCENT }}>Everything included</div>
            <h2 className="max-w-[18ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.2rem,5.5vw,4.5rem)', lineHeight: 1.0 }}>
              The whole business, <span className="italic" style={{ color: ACCENT }}>one tab.</span>
            </h2>
            <p className="mt-6 max-w-lg text-lg leading-relaxed" style={{ color: MUTED }}>
              Not just pages. Gummfit ships with the tools you’d otherwise duct-tape together from
              five subscriptions.
            </p>
          </Reveal>
          <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, idx) => (
              <Reveal key={f.t} delay={idx * 70}>
                <div className="gf-card h-full rounded-2xl border p-7" style={{ borderColor: LINE, background: 'rgba(244,241,232,0.02)' }}>
                  <f.icon size={22} strokeWidth={1.6} style={{ color: ACCENT }} />
                  <h3 className="mt-5 tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.5rem' }}>{f.t}</h3>
                  <p className="mt-2.5 text-[15px] leading-relaxed" style={{ color: MUTED }}>{f.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* offerings as typography */}
      <section className="border-b py-28 sm:py-40" style={{ borderColor: LINE }}>
        <div className={WRAP}>
          <Reveal>
            <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.3em]" style={{ color: ACCENT }}>For a business of one</div>
            <h2 className="max-w-[16ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.2rem,5.5vw,4.5rem)', lineHeight: 1.0 }}>
              One “product.” <span className="italic" style={{ color: ACCENT }}>Any shape.</span>
            </h2>
            <p className="mt-6 max-w-lg text-lg leading-relaxed" style={{ color: MUTED }}>
              Most builders only sell physical goods. Gummfit treats everything you offer as a product you
              price — and handles how it’s delivered.
            </p>
          </Reveal>

          <div className="mt-16 border-t" style={{ borderColor: LINE }}>
            {OFFERINGS.map((o, idx) => (
              <Reveal key={o.n} delay={idx * 80}>
                <div className="group flex items-baseline gap-6 border-b py-7 transition-colors sm:gap-10" style={{ borderColor: LINE }}>
                  <span style={{ fontFamily: DISPLAY, color: ACCENT }} className="text-xl tabular-nums sm:text-2xl">{o.n}</span>
                  <h3 className="min-w-[5.5ch] tracking-tight transition-transform duration-500 group-hover:translate-x-1.5" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(1.9rem,4.5vw,3rem)', lineHeight: 1 }}>{o.t}</h3>
                  <p className="ml-auto max-w-sm text-right text-[15px] leading-relaxed opacity-70 transition-opacity duration-500 group-hover:opacity-100" style={{ color: MUTED }}>{o.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* how it works */}
      <section className="py-28 sm:py-40">
        <div className={WRAP}>
          <Reveal>
            <h2 className="tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2rem,5vw,4rem)', lineHeight: 1.02 }}>
              Live in an <span className="italic" style={{ color: ACCENT }}>afternoon.</span>
            </h2>
            <p className="mt-5 max-w-md text-lg leading-relaxed" style={{ color: MUTED }}>
              Your site goes live at <span style={{ color: INK }}>yourname<span style={{ color: ACCENT }}>.gummfit.com</span></span> the moment you publish.
            </p>
          </Reveal>
          <div className="mt-16 grid gap-x-12 gap-y-14 sm:grid-cols-3">
            {STEPS.map((s, idx) => (
              <Reveal key={s.n} delay={idx * 120}>
                <div className="border-t pt-6" style={{ borderColor: 'rgba(244,241,232,0.25)' }}>
                  <span className="italic" style={{ fontFamily: DISPLAY, color: ACCENT, fontSize: '1.9rem' }}>{s.n}</span>
                  <h3 className="mt-5 tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.7rem', lineHeight: 1.1 }}>{s.t}</h3>
                  <p className="mt-2.5 leading-relaxed" style={{ color: MUTED }}>{s.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* closing */}
      <section className="relative isolate overflow-hidden border-t py-36 text-center sm:py-52" style={{ borderColor: LINE }}>
        <div className="pointer-events-none absolute left-1/2 bottom-[-30%] -z-10 h-[40rem] w-[55rem] -translate-x-1/2 rounded-full blur-[150px]"
          style={{ background: 'radial-gradient(closest-side, rgba(150,200,70,0.20), transparent)' }} />
        <div className={WRAP}>
          <Reveal>
            <h2 className="mx-auto max-w-[16ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.6rem,8vw,6.5rem)', lineHeight: 0.96 }}>
              Turn what you do into a site that <span className="italic" style={{ color: ACCENT }}>sells it.</span>
            </h2>
            <Link to="/cappe/website-setup" className="mt-12 inline-flex items-center rounded-full px-9 py-4 text-[15px] font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
              Create your site →
            </Link>
          </Reveal>
        </div>
      </section>

      <footer className="border-t" style={{ borderColor: LINE }}>
        <div className={`${WRAP} flex items-center justify-between py-8 text-sm`} style={{ color: MUTED }}>
          <span style={{ fontFamily: DISPLAY, color: INK }} className="text-base">Gummfit<span style={{ color: ACCENT }}>.</span></span>
          <span className="text-[11px] uppercase tracking-[0.25em]">A product by Matcha</span>
        </div>
      </footer>
    </div>
  )
}
