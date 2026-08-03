import { Link } from 'react-router-dom'
import { BadgeCheck, Handshake, Sparkles, ShieldCheck } from 'lucide-react'
import { ui } from '../components/ui'

// Public marketing page at /cappe/for-creators. Static, no API — the pitch for
// creators to sign up, plus the creator-first protections summary (Part 9B).
export default function CreatorsLanding() {
  return (
    <div className={ui.page}>
      <header className="border-b border-zinc-800 px-6 py-5">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <Link to="/cappe" className="text-lg font-semibold tracking-tight text-zinc-50">Gummfit</Link>
          <Link to="/cappe/website-setup?type=creator" className={ui.btnPrimary}>Get started</Link>
        </div>
      </header>

      <section className="mx-auto max-w-3xl px-6 pb-16 pt-20 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-zinc-50 sm:text-5xl">
          Get paid to create for brands you love
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-zinc-400">
          Build a media kit, get discovered by brands, negotiate on your terms, and get
          paid — all in one place. We're built to protect creators, not just brands.
        </p>
        <Link to="/cappe/website-setup?type=creator" className={`${ui.btnPrimary} mt-8 px-6 py-3 text-base`}>
          Create your profile
        </Link>
      </section>

      <section className="mx-auto grid max-w-5xl gap-5 px-6 pb-20 sm:grid-cols-3">
        <div className={`${ui.card} p-6`}>
          <Sparkles className="h-5 w-5 text-emerald-400" />
          <h3 className="mt-3 text-base font-semibold text-zinc-100">Build your media kit</h3>
          <p className="mt-1.5 text-sm text-zinc-400">
            Socials, portfolio, and rate card in one profile brands can browse and trust.
          </p>
        </div>
        <div className={`${ui.card} p-6`}>
          <BadgeCheck className="h-5 w-5 text-emerald-400" />
          <h3 className="mt-3 text-base font-semibold text-zinc-100">Get verified reach</h3>
          <p className="mt-1.5 text-sm text-zinc-400">
            We audit your follower counts so your numbers carry real weight in negotiations.
          </p>
        </div>
        <div className={`${ui.card} p-6`}>
          <Handshake className="h-5 w-5 text-emerald-400" />
          <h3 className="mt-3 text-base font-semibold text-zinc-100">Negotiate + get paid</h3>
          <p className="mt-1.5 text-sm text-zinc-400">
            Counter offers, chat terms, and get paid through checkout — no chasing invoices.
          </p>
        </div>
      </section>

      <section className="border-t border-zinc-800 px-6 py-16">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h2 className="text-xl font-semibold text-zinc-50">Creator-first protections</h2>
          </div>
          <ul className="space-y-3 text-sm text-zinc-400">
            <li className="flex gap-2.5">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              Paid usage rights are always time-bound, and whitelisting always counts as paid —
              no perpetual, unpriced ad usage of your content.
            </li>
            <li className="flex gap-2.5">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              If a brand goes quiet on a review, your submission auto-approves after a set window
              so you still get paid on time.
            </li>
            <li className="flex gap-2.5">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              If a brand cancels after you've done approved work, they still owe you for it —
              only unearned installments are forfeited.
            </li>
            <li className="flex gap-2.5">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
              Every offer gets a free Deal Check before you accept — a plain-language read on
              rate, usage terms, and the brand's track record.
            </li>
          </ul>
        </div>
      </section>
    </div>
  )
}
