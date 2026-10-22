import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Camera, Globe, Image as ImageIcon, Mail, Sparkles } from 'lucide-react'
import { fetchCappePricing } from '../../api'
import type { CappePublicPlan } from '../../types'
import { writerPaths } from './writerPaths'

const FEATURES = [
  { icon: BookOpen, title: 'Laid out like print', body: 'Covers, photo essays, pull quotes and interviews, not a wall of text.' },
  { icon: Camera, title: 'Your photos, cleaned', body: 'Location and camera details are removed before anything is stored.' },
  { icon: ImageIcon, title: 'Free pictures, credited', body: 'Search Openverse, the Smithsonian, The Met and NASA; every credit is printed for you.' },
  { icon: Sparkles, title: 'Help that stays honest', body: 'Drafts, headlines and captions from your notes; AI illustrations are always labeled.' },
  { icon: Mail, title: 'Readers by email', body: 'People follow your magazine and get each story you send as an issue.' },
  { icon: Globe, title: 'Your own address', body: 'yourname.gummfit.com from day one, or your own domain.' },
]

const dollars = (cents: number) => `$${(cents / 100).toFixed(cents % 100 ? 2 : 0)}`

/** `/cappe/magazines/start` — Gummfit Magazines for writers. Public. */
export default function WritersLanding() {
  const [plans, setPlans] = useState<CappePublicPlan[] | null>(null)

  useEffect(() => {
    fetchCappePricing('writer').then((p) => setPlans(p.plans)).catch(() => setPlans([]))
  }, [])

  const writer = plans?.find((p) => p.code === 'writer')
  const monthly = writer?.prices.find((p) => p.interval === 'month')

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <span className="text-lg font-semibold tracking-tight">Gummfit Magazines</span>
        <Link to={writerPaths.login} className="text-sm text-zinc-400 hover:text-zinc-100">Sign in</Link>
      </header>
      <main className="mx-auto max-w-5xl px-6 pb-24">
        <section className="py-16 text-center">
          <h1 className="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">Tell it in pictures.</h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-zinc-400">
            Publish your own photo magazine on any subject, from street fashion to city politics, laid out like the
            magazines you grew up with.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link to={writerPaths.signup} className="rounded-lg bg-lime-300 px-5 py-3 text-sm font-semibold text-zinc-950 hover:bg-lime-200">
              Start your magazine
            </Link>
          </div>
          <p className="mt-3 text-xs text-zinc-500">Free to write. {monthly ? `${dollars(monthly.unit_amount_cents)} a month` : 'A small monthly plan'} when you publish.</p>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="What you get">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <Icon className="mb-3 h-5 w-5 text-lime-300" />
              <h2 className="font-medium">{title}</h2>
              <p className="mt-1 text-sm text-zinc-400">{body}</p>
            </div>
          ))}
        </section>

        {plans && plans.length > 0 && (
          <section className="mt-16" aria-label="Plans">
            <h2 className="mb-4 text-center text-2xl font-semibold">Plans</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              {plans.map((p) => {
                const price = p.prices.find((x) => x.interval === 'month')
                return (
                  <div key={p.code} className={`rounded-2xl border p-5 ${p.code === 'writer' ? 'border-lime-300/40 bg-lime-300/[0.04]' : 'border-zinc-800 bg-zinc-900'}`}>
                    <h3 className="font-medium">{p.name}</h3>
                    <p className="mt-1 text-2xl font-semibold">{price ? `${dollars(price.unit_amount_cents)}/mo` : 'Free'}</p>
                    {p.description && <p className="mt-2 text-sm text-zinc-400">{p.description}</p>}
                  </div>
                )
              })}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
