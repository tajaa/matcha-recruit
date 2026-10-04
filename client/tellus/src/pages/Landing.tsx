import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight, Award, Camera, Flame, Gift, MapPin, Menu, Megaphone, MessageSquare,
  QrCode, ShieldCheck, Sparkles, Star, Store, Trophy, X,
} from 'lucide-react'
import { useAccount } from '../hooks/useAccount'
import { HeroTicket } from '../components/landing/HeroTicket'
import { MarqueeTicker } from '../components/landing/MarqueeTicker'
import { AmbientGlow } from '../components/landing/AmbientGlow'
import { TypeHeader, TypedHeadline } from '../components/landing/TypeHeader'
import { ReceiptList } from '../components/landing/ReceiptList'
import { PunchCard } from '../components/landing/PunchCard'
import { RegularsBoard } from '../components/landing/RegularsBoard'
import { VoidTicket } from '../components/landing/VoidTicket'
import { StudioRegisterIllustration, StudioShopScene } from '../components/landing/LandingArtwork'

const REVEAL = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
}

const NAV_LINKS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#regulars-board', label: 'Regulars board' },
  { href: '#for-brands', label: 'For brands' },
]

function Nav() {
  const { account } = useAccount()
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-tu-border/70 bg-tu-bg/75 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Link to="/tellus-app" className="flex items-center gap-2" onClick={() => setOpen(false)}>
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-tu-accent text-sm font-black text-white shadow-[0_5px_12px_rgba(184,102,18,0.2)]">TU</span>
          <span className="font-display text-sm font-bold tracking-tight">Tell-Us</span>
        </Link>

        <nav className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((l) => <a key={l.href} href={l.href} className="text-sm font-medium text-tu-dim transition hover:text-tu-text">{l.label}</a>)}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          {account ? <Link to="/" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-tu-accent-soft">Open app</Link> : <>
            <Link to="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-tu-dim transition hover:text-tu-text">Sign in</Link>
            <Link to="/signup" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-tu-accent-soft">Get started</Link>
          </>}
        </div>

        <button onClick={() => setOpen((v) => !v)} className="-mr-2 flex h-10 w-10 items-center justify-center text-tu-text md:hidden" aria-label={open ? 'Close menu' : 'Open menu'}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && <div className="border-t border-tu-border bg-tu-bg px-5 pb-6 pt-2 md:hidden">
        <div className="flex flex-col">
          {NAV_LINKS.map((l) => <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="border-b border-tu-border/60 py-3 text-sm font-medium text-tu-dim">{l.label}</a>)}
        </div>
        <div className="mt-4 flex flex-col gap-2">
          {account ? <Link to="/" onClick={() => setOpen(false)} className="rounded-lg bg-tu-accent px-4 py-2.5 text-center text-sm font-semibold text-white">Open app</Link> : <>
            <Link to="/signup" onClick={() => setOpen(false)} className="rounded-lg bg-tu-accent px-4 py-2.5 text-center text-sm font-semibold text-white">Get started</Link>
            <Link to="/login" onClick={() => setOpen(false)} className="rounded-lg border border-tu-border px-4 py-2.5 text-center text-sm font-semibold text-tu-text">Sign in</Link>
          </>}
        </div>
      </div>}
    </header>
  )
}

export default function Landing() {
  return (
    <div className="tu-studio min-h-screen bg-tu-bg text-tu-text">
      <Nav />

      <section className="relative overflow-hidden">
        <AmbientGlow />
        <div className="mx-auto grid max-w-6xl items-center gap-16 px-5 pb-20 pt-20 sm:pb-28 sm:pt-28 lg:grid-cols-[1.05fr_0.95fr] lg:gap-12">
          <div className="mx-auto max-w-xl text-center lg:mx-0 lg:text-left">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-accent/30 bg-tu-accent/10 px-3 py-1 font-mono text-xs font-medium text-tu-accent"><Sparkles className="h-3.5 w-3.5" /> No algorithm. Just receipts.</span>
            <TypedHeadline
              className="mt-6 max-w-2xl font-display text-5xl font-semibold leading-[0.98] tracking-[-0.04em] sm:text-7xl"
              segments={[{ text: 'Leave a receipt.' }, { text: 'Get one back.', accent: true, newLine: true }]}
            />
            <p className="mx-auto mt-7 max-w-lg text-base leading-8 text-tu-dim sm:text-lg lg:mx-0">Scan the QR at checkout, leave a review — good, bad, or lukewarm. Every review is tied to a real visit, so nobody buys their way to five stars. Useful feedback prints out in points you can spend at your favorite local places.</p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
              <Link to="/signup" className="inline-flex items-center gap-2 rounded-xl bg-tu-accent px-6 py-3.5 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(184,102,18,0.2)] transition hover:bg-tu-accent-soft">Start your tab <ArrowRight className="h-4 w-4" /></Link>
            </div>
            <p className="mt-5 flex items-center justify-center gap-1.5 text-xs text-tu-faint lg:justify-start"><ShieldCheck className="h-3.5 w-3.5" /> Free for consumers, always.</p>
            <p className="mt-2 text-xs lg:text-left"><Link to="/places" className="text-tu-accent hover:underline">Rate any place — no account needed →</Link></p>
          </div>
          <div className="relative mx-auto w-full max-w-lg">
            <div className="relative z-10"><HeroTicket /></div>
            <StudioShopScene className="relative z-0 -mt-10 w-full opacity-95" />
          </div>
        </div>
      </section>

      <MarqueeTicker />
      <div className="tu-tear-edge-divider" />

      <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-16">
        <div className="mx-auto mb-10 max-w-lg text-center">
          <TypeHeader text="How it works" className="font-display text-2xl font-semibold sm:text-3xl" />
          <p className="mt-2 text-sm text-tu-dim">A useful opinion goes further than a star rating.</p>
        </div>
        <ReceiptList
          eyebrow="Your visit · itemized"
          rows={[
            { icon: Camera, label: 'Give feedback', body: "Scan a store's QR, rate the visit, add a photo or video if you've got one.", value: '+15–150 PTS' },
            { icon: Flame, label: 'Keep the check in', body: 'Come back again — daily streaks and detail both pay more.', value: '×1.5 BONUS' },
            { icon: Gift, label: 'Cash out', body: 'Spend points on real perks at places you actually go — not gift-card purgatory.', value: 'PAID IN POINTS' },
          ]}
          total={{ label: 'Total', value: 'A better local loop' }}
        />
      </section>

      <div className="tu-tear-edge-divider" />

      <section className="mx-auto max-w-6xl px-5 py-16">
        <div className="mx-auto mb-8 max-w-lg text-center">
          <TypeHeader text="Make showing up count" className="font-display text-2xl font-semibold sm:text-3xl" />
          <p className="mt-2 text-sm text-tu-dim">LOYALTY CARD · 4/6 PUNCHED. The good stuff is earned in public.</p>
        </div>
        <PunchCard stamps={[
          { icon: Star, label: 'Level up', punched: true },
          { icon: Flame, label: 'Keep a streak', punched: true },
          { icon: Award, label: 'Unlock badges', punched: true },
          { icon: Trophy, label: 'Top the board', punched: true },
          { icon: MessageSquare, label: 'Leave a review', punched: false },
          { icon: Gift, label: 'Cash out', punched: false },
        ]} />
      </section>

      <div className="tu-tear-edge-divider" />

      <section id="regulars-board" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-16">
        <RegularsBoard notes={[
          { kind: 'deal', title: 'Two-for-one slices after 4.', place: 'Corner Diner', rotate: -2 },
          { kind: 'update', title: 'The oat latte is back.', place: 'Corner Coffee Co.', rotate: 3 },
          { kind: 'event', title: 'Sunday printmaking pop-up.', place: 'The Print Shop', rotate: 2 },
          { kind: 'promo', title: 'Free tote with your first visit.', place: 'The Print Shop', rotate: -3 },
        ]} />
      </section>

      <div className="tu-tear-edge-divider" />

      <section id="for-brands" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-16">
        <motion.div {...REVEAL} transition={{ duration: 0.4 }} className="relative grid items-start gap-10 overflow-hidden rounded-2xl border border-tu-border bg-tu-panel p-8 shadow-[0_24px_60px_rgba(76,55,29,0.12)] sm:p-10 lg:grid-cols-2">
          <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-tu-accent/[0.09] blur-3xl" />
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-border px-3 py-1 font-mono text-xs font-medium text-tu-dim"><Store className="h-3.5 w-3.5" /> For brands & stores</span>
            <TypeHeader text="No algorithm. Just a better loop." className="mt-4 font-display text-2xl font-semibold sm:text-3xl" />
            <p className="mt-3 text-sm leading-relaxed text-tu-dim">Print the QR, hear what actually happened, and give regulars a reason to come back. Tell-Us turns feedback into a local relationship, not another opaque ranking.</p>
            <ul className="mt-5 space-y-2.5">
              {[
                { icon: QrCode, t: 'Per-store QR links', d: 'A clean link for every counter and location.' },
                { icon: MapPin, t: 'Location-based reach', d: 'Know where the visit happened.' },
                { icon: MessageSquare, t: 'Feedback dashboard', d: 'See the signal without the star-rating theater.' },
                { icon: Megaphone, t: 'Post to the board', d: 'Put your next drop in front of regulars.' },
              ].map(({ icon: Icon, t, d }) => <li key={t} className="flex items-start gap-3"><Icon className="mt-0.5 h-4.5 w-4.5 shrink-0 text-tu-accent" /><span className="text-sm text-tu-dim"><span className="font-semibold text-tu-text">{t}.</span> {d}</span></li>)}
            </ul>
            <Link to="/signup" className="mt-6 inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-tu-accent-soft">Set up your brand <ArrowRight className="h-4 w-4" /></Link>
          </div>

          <div className="relative rounded-xl border border-tu-border bg-tu-bg/65 p-5 font-mono shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
            <StudioRegisterIllustration className="pointer-events-none absolute right-4 top-10 w-20 opacity-25" />
            <div className="flex items-center justify-between text-xs text-tu-faint"><span>REGISTER — THIS WEEK</span><span>4 STORES</span></div>
            <div className="mt-4 space-y-1.5 border-t border-dashed border-tu-border pt-3 text-xs">
              {[{ k: 'Positive', v: 62, tone: 'text-tu-good' }, { k: 'Neutral', v: 27, tone: 'text-tu-dim' }, { k: 'Negative', v: 11, tone: 'text-tu-bad' }].map((r) => <div key={r.k} className="flex items-center justify-between"><span className="text-tu-faint">{r.k}</span><span className="flex items-center gap-2"><span className="h-1 w-24 overflow-hidden rounded-full bg-tu-panel2"><span className={`block h-full ${r.tone === 'text-tu-good' ? 'bg-tu-good' : r.tone === 'text-tu-bad' ? 'bg-tu-bad' : 'bg-tu-dim'}`} style={{ width: `${r.v}%` }} /></span><span className={`w-10 text-right font-bold ${r.tone}`}>{r.v}%</span></span></div>)}
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-dashed border-tu-border pt-3 text-xs"><span className="text-tu-faint">Board posts this week</span><span className="font-bold text-tu-accent">8</span></div>
          </div>

          <div className="lg:col-span-2"><VoidTicket before={{ rating: 1, quote: 'Order was wrong, no apology.', meta: 'HELD FOR REVIEW' }} after={{ rating: 4, quote: "Manager reached out, fixed it, we're square.", meta: 'RESOLVED 8:03 AM · PUBLISHED' }} /></div>
        </motion.div>
      </section>

      <div className="tu-tear-edge-divider" />

      <motion.section {...REVEAL} transition={{ duration: 0.4 }} className="relative overflow-hidden px-5 py-20 text-center">
        <AmbientGlow />
        <div className="mx-auto max-w-6xl">
          <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-tu-accent">Total due</p>
          <TypeHeader text="Your opinion is worth something." className="tu-gradient-text mt-3 bg-gradient-to-r from-tu-text via-tu-accent to-tu-text bg-clip-text font-display text-3xl font-semibold text-transparent sm:text-4xl" />
          <p className="mx-auto mt-3 max-w-md text-tu-dim">Open a tab with your city — leave honest feedback, stack points, cash out at the places you already love.</p>
          <motion.span className="mt-7 inline-block" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }}><Link to="/signup" className="inline-flex items-center gap-2 rounded-xl bg-tu-accent px-7 py-3.5 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(184,102,18,0.2)] transition hover:bg-tu-accent-soft">Open your tab <ArrowRight className="h-4 w-4" /></Link></motion.span>
          <p className="mt-4 font-mono text-xs text-tu-faint">No purchase. No catch. No algorithm.</p>
        </div>
      </motion.section>

      <div className="tu-tear-edge-divider" />

      <footer>
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid gap-10 sm:grid-cols-4">
            <div><div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-tu-accent text-xs font-black text-white">TU</span><span className="font-display text-sm font-bold">Tell-Us</span></div><p className="mt-3 max-w-xs text-sm text-tu-dim">Feedback that pays off — for the people giving it, and the brands acting on it.</p></div>
            <div><div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-tu-faint">Get started</div><ul className="space-y-2 text-sm"><li><Link to="/signup" className="text-tu-dim transition hover:text-tu-text">Create an account</Link></li><li><Link to="/login" className="text-tu-dim transition hover:text-tu-text">Sign in</Link></li></ul></div>
            <div><div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-tu-faint">Regulars board</div><ul className="space-y-2 text-sm"><li><a href="#regulars-board" className="text-tu-dim transition hover:text-tu-text">How the board works</a></li><li><Link to="/places" className="text-tu-dim transition hover:text-tu-text">Find a board</Link></li></ul></div>
            <div><div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-tu-faint">For brands</div><ul className="space-y-2 text-sm"><li><a href="#for-brands" className="text-tu-dim transition hover:text-tu-text">Why Tell-Us</a></li><li><Link to="/signup" className="text-tu-dim transition hover:text-tu-text">Set up your brand</Link></li></ul></div>
          </div>
          <div className="mt-10 border-t border-tu-border pt-6 text-xs text-tu-faint">© {new Date().getFullYear()} Tell-Us. All rights reserved.</div>
        </div>
      </footer>
    </div>
  )
}
