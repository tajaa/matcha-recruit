import { Link } from 'react-router-dom'
import { Award, Camera, Flame, Gift, MessageSquare, QrCode, Star, Store, Trophy } from 'lucide-react'
import { useAccount } from '../hooks/useAccount'

function Nav() {
  const { account } = useAccount()
  return (
    <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
      <div className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-tu-accent text-sm font-black text-black">TU</span>
        <span className="text-sm font-bold tracking-tight">Tell-Us</span>
      </div>
      <nav className="flex items-center gap-2">
        {account ? (
          <Link to="/" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-black hover:bg-tu-accent-soft">Open app</Link>
        ) : (
          <>
            <Link to="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-tu-dim hover:text-tu-text">Sign in</Link>
            <Link to="/signup" className="rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-black hover:bg-tu-accent-soft">Get started</Link>
          </>
        )}
      </nav>
    </header>
  )
}

function Step({ icon: Icon, title, body }: { icon: typeof Camera; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-tu-border bg-tu-panel p-6">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-tu-accent/10 text-tu-accent">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-tu-dim">{body}</p>
    </div>
  )
}

export default function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-5 pb-16 pt-10 sm:pt-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-accent/30 bg-tu-accent/10 px-3 py-1 text-xs font-medium text-tu-accent">
            <Star className="h-3.5 w-3.5" /> Feedback that pays off
          </span>
          <h1 className="mt-5 text-4xl font-black leading-tight tracking-tight sm:text-6xl">
            Tell brands what you think.<br /><span className="text-tu-accent">Get rewarded for it.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-tu-dim">
            Share honest feedback about the stores and brands around you — good or bad, with a photo or video.
            Earn points for useful feedback and swap them for real perks in your city.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link to="/signup" className="rounded-lg bg-tu-accent px-6 py-3 text-sm font-semibold text-black hover:bg-tu-accent-soft">Start earning</Link>
            <Link to="/login" className="rounded-lg border border-tu-border px-6 py-3 text-sm font-semibold text-tu-text hover:border-tu-accent">Sign in</Link>
          </div>
        </div>
      </section>

      {/* How it works — consumer */}
      <section className="mx-auto max-w-6xl px-5 py-12">
        <h2 className="mb-8 text-center text-2xl font-bold">How it works</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Step icon={Camera} title="1. Give feedback" body="Scan a store's QR code, rate your experience, and add a photo or video in seconds." />
          <Step icon={Award} title="2. Earn points" body="Useful, detailed feedback earns points. Keep a daily streak and level up as you go." />
          <Step icon={Gift} title="3. Redeem rewards" body="Spend points on local perks — discounts, freebies, and more — in a city marketplace." />
        </div>
      </section>

      {/* Gamification strip */}
      <section className="mx-auto max-w-6xl px-5 py-8">
        <div className="grid grid-cols-2 gap-4 rounded-2xl border border-tu-border bg-tu-panel p-6 sm:grid-cols-4">
          {[
            { icon: Star, label: 'Levels', sub: 'Climb as you contribute' },
            { icon: Flame, label: 'Streaks', sub: 'Come back daily' },
            { icon: Award, label: 'Badges', sub: 'Unlock milestones' },
            { icon: Trophy, label: 'Leaderboards', sub: 'Top your city' },
          ].map(({ icon: Icon, label, sub }) => (
            <div key={label} className="text-center">
              <Icon className="mx-auto mb-2 h-6 w-6 text-tu-accent" />
              <p className="text-sm font-semibold">{label}</p>
              <p className="text-xs text-tu-faint">{sub}</p>
            </div>
          ))}
        </div>
      </section>

      {/* For brands */}
      <section className="mx-auto max-w-6xl px-5 py-12">
        <div className="grid items-center gap-8 rounded-2xl border border-tu-border bg-gradient-to-br from-tu-panel to-tu-bg p-8 sm:grid-cols-2">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-tu-border px-3 py-1 text-xs font-medium text-tu-dim">
              <Store className="h-3.5 w-3.5" /> For brands & stores
            </span>
            <h2 className="mt-4 text-2xl font-bold">Turn feedback into loyalty</h2>
            <p className="mt-2 text-sm text-tu-dim">
              Print a QR code for each location, see honest feedback and sentiment roll up in one dashboard,
              and fund rewards that bring customers back — no complex loyalty stack required.
            </p>
            <Link to="/signup" className="mt-5 inline-block rounded-lg bg-tu-accent px-5 py-2.5 text-sm font-semibold text-black hover:bg-tu-accent-soft">
              Set up your brand
            </Link>
          </div>
          <div className="grid gap-3">
            {[
              { icon: QrCode, t: 'Per-store QR links', d: 'Generate and revoke codes per location.' },
              { icon: MessageSquare, t: 'Feedback dashboard', d: 'Triage by sentiment, category, and store.' },
              { icon: Gift, t: 'Fund rewards', d: 'List perks and verify redemptions at the counter.' },
            ].map(({ icon: Icon, t, d }) => (
              <div key={t} className="flex items-start gap-3 rounded-xl border border-tu-border bg-tu-panel p-4">
                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-tu-accent" />
                <div>
                  <p className="text-sm font-semibold">{t}</p>
                  <p className="text-xs text-tu-dim">{d}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-6xl px-5 py-16 text-center">
        <h2 className="text-3xl font-bold">Your opinion is worth something.</h2>
        <p className="mx-auto mt-3 max-w-md text-tu-dim">Join Tell-Us and start turning everyday feedback into local rewards.</p>
        <Link to="/signup" className="mt-6 inline-block rounded-lg bg-tu-accent px-6 py-3 text-sm font-semibold text-black hover:bg-tu-accent-soft">
          Create your free account
        </Link>
      </section>

      <footer className="border-t border-tu-border py-8 text-center text-xs text-tu-faint">Tell-Us</footer>
    </div>
  )
}
