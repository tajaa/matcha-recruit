import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight, Award, Camera, Flame, Gift, Menu, MessageSquare, QrCode,
  ShieldCheck, Sparkles, Star, Store, Trophy, X,
} from 'lucide-react'
import { useAccount } from '../hooks/useAccount'
import { TicketPanel } from '../components/landing/Ticket'
import { HeroTicket } from '../components/landing/HeroTicket'
import { MarqueeTicker } from '../components/landing/MarqueeTicker'

const REVEAL = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
}

const NAV_LINKS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#for-brands', label: 'For brands' },
]

function Nav() {
  const { account } = useAccount()
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-tu-border/80 bg-tu-bg/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Link to="/tellus-app" className="flex items-center gap-2" onClick={() => setOpen(false)}>
          <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-tu-accent text-sm font-black text-black">TU</span>
          <span className="font-display text-sm font-bold tracking-tight">Tell-Us</span>
        </Link>

        <nav className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className="text-sm font-medium text-tu-dim transition hover:text-tu-text">{l.label}</a>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          {account ? (
            <Link to="/" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">Open app</Link>
          ) : (
            <>
              <Link to="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-tu-dim transition hover:text-tu-text">Sign in</Link>
              <Link to="/signup" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">Get started</Link>
            </>
          )}
        </div>

        <button onClick={() => setOpen((v) => !v)} className="-mr-2 flex h-10 w-10 items-center justify-center text-tu-text md:hidden" aria-label={open ? 'Close menu' : 'Open menu'}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-tu-border bg-tu-bg px-5 pb-6 pt-2 md:hidden">
          <div className="flex flex-col">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="border-b border-tu-border/60 py-3 text-sm font-medium text-tu-dim">{l.label}</a>
            ))}
          </div>
          <div className="mt-4 flex flex-col gap-2">
            {account ? (
              <Link to="/" onClick={() => setOpen(false)} className="rounded-lg bg-tu-accent px-4 py-2.5 text-center text-sm font-semibold text-black">Open app</Link>
            ) : (
              <>
                <Link to="/signup" onClick={() => setOpen(false)} className="rounded-lg bg-tu-accent px-4 py-2.5 text-center text-sm font-semibold text-black">Get started</Link>
                <Link to="/login" onClick={() => setOpen(false)} className="rounded-lg border border-tu-border px-4 py-2.5 text-center text-sm font-semibold text-tu-text">Sign in</Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  )
}

function Step({ n, icon: Icon, title, body }: { n: number; icon: typeof Camera; title: string; body: string }) {
  return (
    <TicketPanel
      {...REVEAL}
      transition={{ duration: 0.4, delay: n * 0.1 }}
      className="bg-tu-paper p-6 pb-8 text-tu-ink"
    >
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-sm bg-tu-ink/10 text-tu-ink"><Icon className="h-5 w-5" /></span>
        <span className="font-mono text-xs font-semibold text-tu-ink/50">STEP {n}</span>
      </div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-tu-ink/70">{body}</p>
    </TicketPanel>
  )
}

export default function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10" style={{ background: 'radial-gradient(ellipse 70% 55% at 50% -10%, rgba(249,115,22,0.14) 0%, rgba(249,115,22,0) 60%)' }} />
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-14 pt-14 sm:pt-20 lg:grid-cols-[1.1fr_0.9fr] lg:gap-8">
          <div className="mx-auto max-w-xl text-center lg:mx-0 lg:text-left">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-accent/30 bg-tu-accent/10 px-3 py-1 font-mono text-xs font-medium text-tu-accent">
              <Sparkles className="h-3.5 w-3.5" /> Feedback that pays off
            </span>
            <h1 className="mt-5 font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
              Tell brands what you think.<br /><span className="text-tu-accent">Get rewarded for it.</span>
            </h1>
            <p className="mx-auto mt-5 max-w-lg text-lg leading-relaxed text-tu-dim lg:mx-0">
              Share honest feedback about the stores and brands around you — good or bad, with a photo or video.
              Earn points for useful feedback and swap them for real perks in your city.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
              <Link to="/signup" className="inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-6 py-3 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">
                Start earning <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/login" className="rounded-lg border border-tu-border px-6 py-3 text-sm font-semibold text-tu-text transition hover:border-tu-accent">Sign in</Link>
            </div>
            <p className="mt-5 flex items-center justify-center gap-1.5 text-xs text-tu-faint lg:justify-start">
              <ShieldCheck className="h-3.5 w-3.5" /> Free for consumers, always.
            </p>
          </div>
          <HeroTicket />
        </div>
      </section>

      <MarqueeTicker />

      {/* How it works — consumer */}
      <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-16">
        <div className="mx-auto mb-10 max-w-lg text-center">
          <h2 className="font-display text-2xl font-semibold sm:text-3xl">How it works</h2>
          <p className="mt-2 text-sm text-tu-dim">Three steps between an opinion and a reward.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Step n={1} icon={Camera} title="Give feedback" body="Scan a store's QR code, rate your experience, and add a photo or video in seconds." />
          <Step n={2} icon={Award} title="Earn points" body="Useful, detailed feedback earns points. Keep a daily streak and level up as you go." />
          <Step n={3} icon={Gift} title="Redeem rewards" body="Spend points on local perks — discounts, freebies, and more — in a city marketplace." />
        </div>
      </section>

      {/* Gamification strip */}
      <section className="mx-auto max-w-6xl px-5 py-8">
        <motion.div {...REVEAL} transition={{ duration: 0.4 }} className="grid grid-cols-2 gap-3 rounded-sm border border-tu-border bg-tu-panel p-6 sm:grid-cols-4 sm:gap-4">
          {[
            { icon: Star, label: 'Levels', sub: 'Climb as you contribute' },
            { icon: Flame, label: 'Streaks', sub: 'Come back daily' },
            { icon: Award, label: 'Badges', sub: 'Unlock milestones' },
            { icon: Trophy, label: 'Leaderboards', sub: 'Top your city' },
          ].map(({ icon: Icon, label, sub }, i) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.35, delay: i * 0.08 }}
              className="rounded-sm px-2 py-3 text-center transition hover:bg-tu-panel2"
            >
              <Icon className="mx-auto mb-2 h-6 w-6 text-tu-accent" />
              <p className="text-sm font-semibold">{label}</p>
              <p className="text-xs text-tu-faint">{sub}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* For brands */}
      <section id="for-brands" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-16">
        <motion.div {...REVEAL} transition={{ duration: 0.4 }} className="grid items-center gap-10 rounded-sm border border-tu-border bg-tu-panel p-8 sm:p-10 lg:grid-cols-2">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-border px-3 py-1 font-mono text-xs font-medium text-tu-dim">
              <Store className="h-3.5 w-3.5" /> For brands & stores
            </span>
            <h2 className="mt-4 font-display text-2xl font-semibold sm:text-3xl">Turn feedback into loyalty</h2>
            <p className="mt-3 text-sm leading-relaxed text-tu-dim">
              Print a QR code for each location, see honest feedback and sentiment roll up in one dashboard,
              and fund rewards that bring customers back — no complex loyalty stack required.
            </p>
            <ul className="mt-5 space-y-2.5">
              {[
                { icon: QrCode, t: 'Per-store QR links', d: 'Generate and revoke codes per location.' },
                { icon: MessageSquare, t: 'Feedback dashboard', d: 'Triage by sentiment, category, and store.' },
                { icon: Gift, t: 'Auto or manual rewards', d: 'Approve every payout yourself, or let the rules run.' },
              ].map(({ icon: Icon, t, d }) => (
                <li key={t} className="flex items-start gap-3">
                  <Icon className="mt-0.5 h-4.5 w-4.5 shrink-0 text-tu-accent" />
                  <span className="text-sm text-tu-dim"><span className="font-semibold text-tu-text">{t}.</span> {d}</span>
                </li>
              ))}
            </ul>
            <Link to="/signup" className="mt-6 inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">
              Set up your brand <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* POS-style readout — illustrative, not live data */}
          <div className="rounded-sm border border-tu-border bg-tu-bg p-5 font-mono">
            <div className="flex items-center justify-between text-xs text-tu-faint">
              <span>FEEDBACK — THIS WEEK</span>
              <span>4 STORES</span>
            </div>
            <div className="mt-4 space-y-1.5 border-t border-dashed border-tu-border pt-3 text-xs">
              {[
                { k: 'Positive', v: 62, tone: 'text-tu-good' },
                { k: 'Neutral', v: 27, tone: 'text-tu-dim' },
                { k: 'Negative', v: 11, tone: 'text-tu-bad' },
              ].map((r) => (
                <div key={r.k} className="flex items-center justify-between">
                  <span className="text-tu-faint">{r.k}</span>
                  <span className="flex items-center gap-2">
                    <span className="h-1 w-24 overflow-hidden rounded-full bg-tu-panel2">
                      <span className={`block h-full ${r.tone === 'text-tu-good' ? 'bg-tu-good' : r.tone === 'text-tu-bad' ? 'bg-tu-bad' : 'bg-tu-dim'}`} style={{ width: `${r.v}%` }} />
                    </span>
                    <span className={`w-10 text-right font-bold ${r.tone}`}>{r.v}%</span>
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-dashed border-tu-border pt-3 text-xs">
              <span className="text-tu-faint">Pending reward approvals</span>
              <span className="font-bold text-tu-accent">3</span>
            </div>
          </div>
        </motion.div>
      </section>

      {/* Final CTA */}
      <motion.section {...REVEAL} transition={{ duration: 0.4 }} className="mx-auto max-w-6xl px-5 py-20 text-center">
        <h2 className="font-display text-3xl font-semibold sm:text-4xl">Your opinion is worth something.</h2>
        <p className="mx-auto mt-3 max-w-md text-tu-dim">Join Tell-Us and start turning everyday feedback into local rewards.</p>
        <motion.span className="mt-7 inline-block" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }}>
          <Link to="/signup" className="inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-7 py-3.5 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">
            Create your free account <ArrowRight className="h-4 w-4" />
          </Link>
        </motion.span>
      </motion.section>

      <footer>
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid gap-10 sm:grid-cols-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-tu-accent text-xs font-black text-black">TU</span>
                <span className="font-display text-sm font-bold">Tell-Us</span>
              </div>
              <p className="mt-3 max-w-xs text-sm text-tu-dim">Feedback that pays off — for the people giving it, and the brands acting on it.</p>
            </div>
            <div>
              <div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-tu-faint">Get started</div>
              <ul className="space-y-2 text-sm">
                <li><Link to="/signup" className="text-tu-dim transition hover:text-tu-text">Create an account</Link></li>
                <li><Link to="/login" className="text-tu-dim transition hover:text-tu-text">Sign in</Link></li>
              </ul>
            </div>
            <div>
              <div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-tu-faint">For brands</div>
              <ul className="space-y-2 text-sm">
                <li><a href="#for-brands" className="text-tu-dim transition hover:text-tu-text">Why Tell-Us</a></li>
                <li><Link to="/signup" className="text-tu-dim transition hover:text-tu-text">Set up your brand</Link></li>
              </ul>
            </div>
          </div>
          <div className="mt-10 border-t border-tu-border pt-6 text-xs text-tu-faint">© {new Date().getFullYear()} Tell-Us. All rights reserved.</div>
        </div>
      </footer>
    </div>
  )
}
