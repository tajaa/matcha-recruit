import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, Package, Download, Sparkles, CalendarClock, Layout, MousePointerClick,
  Rocket, Check, Globe, ShieldCheck,
} from 'lucide-react'

const API = `${import.meta.env.VITE_API_URL ?? '/api'}/cappe`
const DESIGN_W = 1280
const DESIGN_H = 820

type TemplateSummary = { id: string; name: string; slug: string; category: string; description: string | null }

/** Scaled, non-interactive live render of a template (reuses the public preview
 *  endpoint). Measures its container so it always fits. */
function TemplateFrame({ slug, name, className = '' }: { slug: string; name: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.3)
  const [loaded, setLoaded] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setScale(el.clientWidth / DESIGN_W)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div ref={ref} className={`relative w-full overflow-hidden ${className}`} style={{ height: DESIGN_H * scale }}>
      <iframe
        title={`${name} preview`}
        src={`${API}/templates/${slug}/preview`}
        sandbox="allow-scripts"
        loading="lazy"
        tabIndex={-1}
        onLoad={() => setLoaded(true)}
        className="pointer-events-none origin-top-left border-0"
        style={{ width: DESIGN_W, height: DESIGN_H, transform: `scale(${scale})`, opacity: loaded ? 1 : 0, transition: 'opacity .4s' }}
      />
    </div>
  )
}

const FULFILLMENTS = [
  { icon: Package, title: 'Physical goods', body: 'Ship products with real inventory.', eg: 'prints · merch · gear' },
  { icon: Download, title: 'Digital downloads', body: 'Sell a file they get instantly after paying.', eg: 'an HR handbook · presets · templates' },
  { icon: Sparkles, title: 'Services & packages', body: 'Take the order, deliver the result, mark it done.', eg: 'a consultant’s report · a wedding photo package' },
  { icon: CalendarClock, title: 'Bookable sessions', body: 'They pick an open slot on your calendar.', eg: 'a training session · a 1:1 consult' },
]

const PERSONAS = [
  'Photographers', 'Chefs', 'Consultants', 'Personal trainers', 'Pilates studios',
  'Nutritionists', 'Designers', 'Coaches', 'Tutors', 'Florists',
]

const STEPS = [
  { icon: Layout, title: 'Pick a template', body: 'Start from a designed, ready-to-edit site — portfolio, storefront, studio, or blog.' },
  { icon: MousePointerClick, title: 'Make it yours', body: 'Edit every block live, add your products, set your prices, upload your work.' },
  { icon: Rocket, title: 'Publish & get paid', body: 'Go live on your own subdomain — visitors buy, book, and download right there.' },
]

export default function CappeLanding() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([])

  useEffect(() => {
    fetch(`${API}/templates`).then((r) => (r.ok ? r.json() : [])).then(setTemplates).catch(() => {})
  }, [])

  const hero = templates.find((t) => t.slug === 'personal-portfolio') || templates[0]

  return (
    <div className="min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-100 antialiased">
      {/* ambient gradient mesh */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute left-1/2 top-[-10%] h-[40rem] w-[60rem] -translate-x-1/2 rounded-full bg-emerald-500/15 blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] h-[36rem] w-[36rem] rounded-full bg-teal-500/10 blur-[120px]" />
        <div className="absolute left-[-10%] top-[40%] h-[30rem] w-[30rem] rounded-full bg-emerald-400/5 blur-[100px]" />
      </div>

      {/* top bar (page-local; intentionally NOT in the matcha nav) */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-bold text-zinc-950 shadow-lg shadow-emerald-500/25">C</span>
          <span className="text-lg font-semibold tracking-tight">Cappe</span>
          <span className="ml-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-400">by Matcha</span>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/cappe/login" className="rounded-lg px-3.5 py-2 text-sm font-medium text-zinc-300 hover:text-white">Sign in</Link>
          <Link to="/cappe/website-setup" className="rounded-lg bg-emerald-500 px-3.5 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-400">Get started</Link>
        </div>
      </header>

      {/* hero */}
      <section className="mx-auto max-w-6xl px-6 pb-10 pt-12 text-center sm:pt-20">
        <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-300">
          <Sparkles className="h-3.5 w-3.5 text-emerald-400" /> A new product by Matcha
        </div>
        <h1 className="mx-auto max-w-4xl text-4xl font-bold leading-[1.05] tracking-tight sm:text-6xl md:text-7xl">
          A website + storefront for a{' '}
          <span className="bg-gradient-to-r from-emerald-300 via-emerald-400 to-teal-300 bg-clip-text text-transparent">business of one.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-zinc-400">
          Cappe lets anyone build a beautiful site and sell <span className="text-zinc-200">whatever they offer</span> —
          a product, a download, a service, or a booked session. You set the price. No code, no plugins, no wrestling.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/cappe/website-setup" className="group inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-6 py-3.5 text-sm font-semibold text-zinc-950 shadow-lg shadow-emerald-500/20 transition hover:bg-emerald-400">
            Start building <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </Link>
          <Link to="/cappe/templates" className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-6 py-3.5 text-sm font-semibold text-zinc-200 transition hover:bg-white/10">
            Browse templates
          </Link>
        </div>

        {/* browser mock with a live template inside */}
        <div className="mx-auto mt-16 max-w-5xl">
          <div className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/60 shadow-2xl shadow-emerald-500/5 backdrop-blur">
            <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
              <span className="h-3 w-3 rounded-full bg-red-400/70" />
              <span className="h-3 w-3 rounded-full bg-amber-400/70" />
              <span className="h-3 w-3 rounded-full bg-emerald-400/70" />
              <div className="mx-auto flex items-center gap-1.5 rounded-md bg-white/5 px-3 py-1 text-xs text-zinc-400">
                <Globe className="h-3 w-3" /> yourbrand.cappe.site
              </div>
            </div>
            {hero ? (
              <TemplateFrame slug={hero.slug} name={hero.name} />
            ) : (
              <div className="aspect-[16/10] w-full animate-pulse bg-zinc-900" />
            )}
          </div>
        </div>
      </section>

      {/* one product, any shape */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">One “product.” Anything you sell.</h2>
          <p className="mt-3 text-zinc-400">Most builders only do physical goods. Cappe treats everything as a product you price — and handles how it’s delivered.</p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FULFILLMENTS.map((f) => (
            <div key={f.title} className="group rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-emerald-500/30 hover:bg-white/[0.06]">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold text-zinc-100">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{f.body}</p>
              <p className="mt-3 text-xs text-emerald-400/80">{f.eg}</p>
            </div>
          ))}
        </div>
      </section>

      {/* who it's for */}
      <section className="mx-auto max-w-5xl px-6 py-12 text-center">
        <p className="text-sm font-medium uppercase tracking-widest text-zinc-500">Made for</p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5">
          {PERSONAS.map((p) => (
            <span key={p} className="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm text-zinc-300">{p}</span>
          ))}
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1.5 text-sm font-medium text-emerald-300">…and you</span>
        </div>
      </section>

      {/* how it works */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Live in an afternoon.</h2>
          <p className="mt-3 text-zinc-400">No templates to wire up, no payment plugins to configure.</p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={s.title} className="relative rounded-2xl border border-white/10 bg-white/[0.03] p-7">
              <div className="mb-5 flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20"><s.icon className="h-4 w-4" /></span>
                <span className="text-sm font-semibold text-zinc-500">Step {i + 1}</span>
              </div>
              <h3 className="text-lg font-semibold text-zinc-100">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-400">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* template showcase */}
      {templates.length > 0 && (
        <section className="mx-auto max-w-6xl px-6 py-12">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Designed templates, not blank pages.</h2>
            <p className="mt-3 text-zinc-400">Every one is editable down to the block. These are live renders.</p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            {templates.slice(0, 4).map((t) => (
              <div key={t.id} className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/50">
                <TemplateFrame slug={t.slug} name={t.name} className="border-b border-white/10" />
                <div className="flex items-center justify-between p-5">
                  <div>
                    <h3 className="font-medium text-zinc-100">{t.name}</h3>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">{t.category}</p>
                  </div>
                  <Link to="/cappe/website-setup" className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:bg-white/10">Use this</Link>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* trust strip */}
      <section className="mx-auto max-w-4xl px-6 py-16">
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            { icon: Globe, t: 'Your own domain', d: 'Free subdomain now, bring your own later.' },
            { icon: ShieldCheck, t: 'Sales built in', d: 'Orders, bookings, and downloads — no add-ons.' },
            { icon: Check, t: 'No code', d: 'Edit live with a real preview as you type.' },
          ].map((x) => (
            <div key={x.t} className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <x.icon className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
              <div>
                <div className="text-sm font-semibold text-zinc-100">{x.t}</div>
                <div className="text-xs text-zinc-400">{x.d}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* final CTA */}
      <section className="mx-auto max-w-5xl px-6 py-20">
        <div className="relative overflow-hidden rounded-3xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-zinc-900 to-zinc-900 p-12 text-center">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(40rem_20rem_at_50%_-20%,rgba(16,185,129,0.18),transparent)]" />
          <h2 className="relative text-3xl font-bold tracking-tight sm:text-5xl">Turn what you do into a site that sells it.</h2>
          <p className="relative mx-auto mt-4 max-w-xl text-zinc-400">Build your Cappe site free. Publish when it’s ready.</p>
          <div className="relative mt-8 flex justify-center">
            <Link to="/cappe/website-setup" className="group inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-7 py-3.5 text-sm font-semibold text-zinc-950 shadow-lg shadow-emerald-500/20 transition hover:bg-emerald-400">
              Create your site <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 py-10 text-center text-sm text-zinc-500">
        <div className="flex items-center justify-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-br from-emerald-400 to-emerald-600 text-[10px] font-bold text-zinc-950">C</span>
          Cappe — a product by Matcha
        </div>
      </footer>
    </div>
  )
}
