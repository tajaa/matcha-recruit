import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingBag, CalendarClock, Mail, ClipboardList, PenLine, BarChart3 } from 'lucide-react'
import { fetchCappeDirectory } from '../api'
import DirectoryCard from '../components/DirectoryCard'
import type { CappeDirectoryEntry } from '../types'

// Gummfit landing — dark, type-led, one electric accent. Fraunces (display) +
// Roboto Flex (body) are loaded globally; visuals are pure CSS (no imagery).
const BG = '#0A0A09'
const INK = '#F4F1E8'
const MUTED = '#8E8B81'
const LINE = 'rgba(244,241,232,0.10)'
const ACCENT = '#C6F16B'
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

/** Live strip of real published sites.
 *
 *  The pitch on this page is "build here and get found", so the proof has to be
 *  actual businesses, not a mock. Renders nothing at all when the directory is
 *  empty or unreachable — an empty "Discover" section would undercut the claim
 *  it exists to make, and this is marketing copy, not a dashboard. */
function DiscoverStrip() {
  const [entries, setEntries] = useState<CappeDirectoryEntry[]>([])
  const [total, setTotal] = useState(0)

  useEffect(() => {
    fetchCappeDirectory({ limit: 6, sort: 'newest' })
      .then((page) => { setEntries(page.entries); setTotal(page.total) })
      .catch(() => setEntries([]))
  }, [])

  if (entries.length === 0) return null

  return (
    <section className="border-b py-28 sm:py-36" style={{ borderColor: LINE }}>
      <div className={WRAP}>
        <Reveal>
          <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.3em]" style={{ color: ACCENT }}>
            Discover
          </div>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <h2 className="max-w-[18ch] tracking-tight" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.2rem,5.5vw,4.5rem)', lineHeight: 1.0 }}>
                You’re not just <span className="italic" style={{ color: ACCENT }}>online.</span>
              </h2>
              <p className="mt-6 max-w-lg text-lg leading-relaxed" style={{ color: MUTED }}>
                Every site published here lands in a directory people actually search.
                {total > 6 ? ` ${total} businesses so far` : ' The newest ones'} — shops,
                studios, and people you can hire directly.
              </p>
            </div>
            <Link
              to="/gummfit/discover"
              className="shrink-0 rounded-full border px-5 py-2.5 text-sm transition-colors hover:text-white"
              style={{ borderColor: LINE, color: MUTED }}
            >
              Browse all →
            </Link>
          </div>
        </Reveal>
        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry, idx) => (
            <Reveal key={entry.slug} delay={idx * 70}>
              <DirectoryCard entry={entry} />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

/** Pure-CSS browser-window mock of a live Gummfit shop — no imagery needed. */
function SiteMock() {
  return (
    <div className="mx-auto mt-16 w-full max-w-4xl" style={{ animation: 'gfFloat 7s ease-in-out infinite' }}>
      <div className="overflow-hidden rounded-[1.35rem] border shadow-[0_40px_120px_-30px_rgba(198,241,107,0.24)]"
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
        {/* a real-feeling storefront, not a wireframe */}
        <div className="grid min-h-[20rem] grid-cols-[0.86fr_1.14fr] sm:min-h-[25rem]">
          <div className="flex flex-col justify-between border-r p-5 sm:p-7" style={{ borderColor: LINE, background: 'rgba(244,241,232,0.025)' }}>
            <div>
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em]" style={{ color: ACCENT }}><span className="h-2 w-2 rounded-full" style={{ background: ACCENT }} /> Live storefront</div>
              <p className="mt-7 max-w-[13ch] tracking-tight" style={{ fontFamily: DISPLAY, fontSize: 'clamp(1.55rem,3vw,2.4rem)', lineHeight: .96 }}>Sora Studio<br /><span className="italic" style={{ color: ACCENT }}>for your space.</span></p>
              <p className="mt-5 hidden max-w-[18ch] text-xs leading-relaxed sm:block" style={{ color: MUTED }}>Objects and small rituals for a slower, more beautiful morning.</p>
            </div>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.15em]" style={{ color: MUTED }}><span className="h-7 w-7 rounded-full border p-2" style={{ borderColor: LINE }}>↗</span> View collection</div>
          </div>
          <div className="relative overflow-hidden p-4 sm:p-6" style={{ background: 'linear-gradient(135deg, #C6E1A0 0%, #EAE2C8 48%, #C4B1D9 100%)' }}>
            <div className="absolute -right-8 -top-10 h-40 w-40 rounded-full bg-[#e79c74]/70 blur-[1px] sm:h-56 sm:w-56" />
            <div className="absolute -bottom-24 -left-14 h-52 w-52 rounded-full bg-[#63805d]/80" />
            <div className="relative ml-auto flex max-w-[13rem] flex-col rounded-xl bg-[#f6f2e7]/95 p-3 shadow-[0_18px_45px_rgba(55,48,36,0.22)] sm:max-w-[15rem] sm:p-4">
              <div className="relative aspect-[1.15] overflow-hidden rounded-lg bg-[#e2ba93]">
                <div className="absolute bottom-0 left-1/2 h-[85%] w-[38%] -translate-x-1/2 rounded-t-[3rem] bg-[#a35e3d]" />
                <div className="absolute bottom-[20%] left-1/2 h-5 w-[60%] -translate-x-1/2 rounded-full bg-[#f0d0a6]" />
                <div className="absolute bottom-[11%] left-1/2 h-4 w-[74%] -translate-x-1/2 rounded-full bg-[#814b34]" />
              </div>
              <div className="mt-3 flex items-start justify-between gap-2 text-left"><div><p className="text-[11px] font-semibold text-[#24251e]">Ritual coffee set</p><p className="mt-0.5 text-[10px] text-[#77776d]">Handmade ceramic</p></div><span className="text-[11px] font-semibold text-[#24251e]">$68</span></div>
              <button className="mt-3 rounded-md py-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#17200f]" style={{ background: ACCENT }}>Add to cart</button>
            </div>
            <div className="absolute bottom-5 left-5 rounded-full bg-[#11130e]/85 px-3 py-2 text-[10px] font-medium tracking-wide text-[#f4f1e8] shadow-lg">Checkout, bookings &amp; more</div>
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
          <Link to="/gummfit/creators" className="hidden transition-colors hover:text-white md:block" style={{ color: MUTED }}>Creators</Link>
          <Link to="/gummfit/discover" className="transition-colors hover:text-white" style={{ color: MUTED }}>Discover</Link>
          <Link to="/gummfit/templates" className="hidden transition-colors hover:text-white sm:block" style={{ color: MUTED }}>Templates</Link>
          <Link to="/gummfit/login" className="transition-colors hover:text-white" style={{ color: MUTED }}>Sign in</Link>
          <Link to="/gummfit/website-setup" className="rounded-full px-5 py-2.5 font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
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
            Your business, beautifully online
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
            <Link to="/gummfit/website-setup" className="inline-flex h-12 items-center rounded-full px-7 text-[15px] font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
              Start building — it’s free
            </Link>
            <Link to="/gummfit/templates" className="inline-flex h-12 items-center text-[15px] transition-colors hover:text-white" style={{ color: MUTED }}>
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

      {/* discover — live directory strip */}
      <DiscoverStrip />

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
            <Link to="/gummfit/website-setup" className="mt-12 inline-flex items-center rounded-full px-9 py-4 text-[15px] font-medium transition-all hover:brightness-110" style={{ background: ACCENT, color: '#10120A' }}>
              Create your site →
            </Link>
          </Reveal>
        </div>
      </section>

      <footer className="border-t" style={{ borderColor: LINE }}>
        <div className={`${WRAP} flex items-center justify-between py-8 text-sm`} style={{ color: MUTED }}>
          <span style={{ fontFamily: DISPLAY, color: INK }} className="text-base">Gummfit<span style={{ color: ACCENT }}>.</span></span>
          <div className="flex items-center gap-5"><Link to="/gummfit/creators" className="transition-colors hover:text-white">Gummfit Creators</Link><span className="text-[11px] uppercase tracking-[0.25em]">A product by Matcha</span></div>
        </div>
      </footer>
    </div>
  )
}
