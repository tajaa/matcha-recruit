import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

// Dark, warm, type-led. Fraunces (display) + Roboto Flex (body) are already
// loaded globally; we lean on kinetic typography + motion, no imagery.
const BG = '#0E0E0C'
const INK = '#F4F1E8'
const MUTED = '#928E83'
const LINE = 'rgba(244,241,232,0.12)'
const ACCENT = '#AECB9E'
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
    <span key={i} className="italic" style={{ color: ACCENT, animation: 'czWord .6s cubic-bezier(.2,.7,.2,1) both', display: 'inline-block' }}>
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

export default function CappeLanding() {
  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <style>{`
        @keyframes czRise{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
        .cz-rise{animation:czRise 1s cubic-bezier(.2,.7,.2,1) both}
        @keyframes czWord{from{opacity:0;transform:translateY(.45em)}to{opacity:1;transform:none}}
        @keyframes czMarquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
        .cz-marquee{animation:czMarquee 38s linear infinite}
        .cz-marquee:hover{animation-play-state:paused}
        @keyframes czGlow{0%,100%{opacity:.5;transform:translate(-50%,0) scale(1)}50%{opacity:.8;transform:translate(-50%,-4%) scale(1.08)}}
      `}</style>

      {/* nav */}
      <header className={`relative z-20 flex items-center justify-between py-7 ${WRAP}`}>
        <div className="flex items-baseline gap-3">
          <span style={{ fontFamily: DISPLAY }} className="text-2xl font-semibold tracking-tight">Cappe</span>
          <span className="text-[11px] uppercase tracking-[0.25em]" style={{ color: MUTED }}>by Matcha</span>
        </div>
        <div className="flex items-center gap-7 text-sm">
          <Link to="/cappe/login" className="transition-colors hover:text-white" style={{ color: MUTED }}>Sign in</Link>
          <Link to="/cappe/website-setup" className="rounded-full bg-white px-5 py-2.5 font-medium transition-colors hover:bg-[#AECB9E]" style={{ color: INK }}>Start building</Link>
        </div>
      </header>

      {/* hero */}
      <section className="relative isolate">
        {/* one soft, slow matcha glow — the only ambient effect */}
        <div className="pointer-events-none absolute left-1/2 top-[-14%] -z-10 h-[44rem] w-[60rem] rounded-full blur-[140px]"
          style={{ background: 'radial-gradient(closest-side, rgba(108,150,96,0.22), transparent)', animation: 'czGlow 9s ease-in-out infinite' }} />
        <div className={`${WRAP} pb-24 pt-16 text-center sm:pb-32 sm:pt-24`}>
          <p className="cz-rise text-[11px] uppercase tracking-[0.34em]" style={{ color: ACCENT }}>A new product by Matcha</p>
          <h1 className="cz-rise mx-auto mt-7 max-w-[18ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.9rem,8.5vw,7rem)', lineHeight: 0.95, animationDelay: '90ms' }}>
            A website that sells{' '}
            <span className="block sm:inline"><Cycle words={SELLS} /></span>
          </h1>
          <p className="cz-rise mx-auto mt-8 max-w-xl text-lg leading-relaxed" style={{ color: MUTED, animationDelay: '180ms' }}>
            Cappe turns your craft into a site and a storefront — products, downloads, services, bookings.
            You set the price. No code, no plugins.
          </p>
          <div className="cz-rise mt-11 flex items-center justify-center gap-6" style={{ animationDelay: '260ms' }}>
            <Link to="/cappe/website-setup" className="inline-flex h-12 items-center rounded-full bg-white px-7 text-[15px] font-medium transition-colors hover:bg-[#AECB9E]" style={{ color: INK }}>
              Start building
            </Link>
            <Link to="/cappe/templates" className="inline-flex h-12 items-center text-[15px] transition-colors hover:text-white" style={{ color: MUTED }}>
              See templates →
            </Link>
          </div>
        </div>
      </section>

      {/* kinetic persona marquee */}
      <div className="relative flex overflow-hidden border-y py-7" style={{ borderColor: LINE }}>
        <div className="cz-marquee flex shrink-0 whitespace-nowrap">
          {[...PERSONAS, ...PERSONAS].map((p, i) => (
            <span key={i} style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(1.4rem,3.4vw,2.6rem)' }}
              className={i % 3 === 1 ? 'mx-7' : 'mx-7'}>
              <span style={{ color: i % 4 === 0 ? ACCENT : MUTED }}>{p}</span>
              <span className="mx-7" style={{ color: 'rgba(244,241,232,0.22)' }}>/</span>
            </span>
          ))}
        </div>
      </div>

      {/* concept + offerings as typography */}
      <section className="border-b py-28 sm:py-40" style={{ borderColor: LINE }}>
        <div className={WRAP}>
          <Reveal>
            <div className="mb-3 text-[11px] font-medium uppercase tracking-wider" style={{ color: ACCENT }}>For a business of one</div>
            <h2 className="max-w-[16ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.2rem,5.5vw,4.5rem)', lineHeight: 1.0 }}>
              One “product.” <span className="italic" style={{ color: ACCENT }}>Any shape.</span>
            </h2>
            <p className="mt-6 max-w-lg text-lg leading-relaxed" style={{ color: MUTED }}>
              Most builders only sell physical goods. Cappe treats everything you offer as a product you price —
              and handles how it’s delivered.
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
          style={{ background: 'radial-gradient(closest-side, rgba(108,150,96,0.22), transparent)' }} />
        <div className={WRAP}>
          <Reveal>
            <h2 className="mx-auto max-w-[16ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.6rem,8vw,6.5rem)', lineHeight: 0.96 }}>
              Turn what you do into a site that <span className="italic" style={{ color: ACCENT }}>sells it.</span>
            </h2>
            <Link to="/cappe/website-setup" className="mt-12 inline-flex items-center rounded-full bg-white px-9 py-4 text-[15px] font-medium transition-colors hover:bg-[#AECB9E]" style={{ color: INK }}>
              Create your site →
            </Link>
          </Reveal>
        </div>
      </section>

      <footer className="border-t" style={{ borderColor: LINE }}>
        <div className={`${WRAP} flex items-center justify-between py-8 text-sm`} style={{ color: MUTED }}>
          <span style={{ fontFamily: DISPLAY, color: INK }} className="text-base">Cappe</span>
          <span className="text-[11px] uppercase tracking-[0.25em]">A product by Matcha</span>
        </div>
      </footer>
    </div>
  )
}
