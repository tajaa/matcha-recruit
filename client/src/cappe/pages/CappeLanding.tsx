import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Menu, X } from 'lucide-react'
import { fetchCappeDirectory } from '../api'
import DirectoryCard from '../components/DirectoryCard'
import type { CappeDirectoryEntry } from '../types'
import Faq from './landing/Faq'
import Features from './landing/Features'
import Hero from './landing/Hero'
import Pricing from './landing/Pricing'
import StackComparison from './landing/StackComparison'
import { EYEBROW, LIME_BUTTON, SIGNUP_PATH, WRAP, usePublicPricing, useReveal } from './landing/shared'

// Every module named here ships in-house — see routes.tsx. That list IS the pitch.
const IN_HOUSE = ['Websites', 'Online stores', 'Bookings', 'Newsletters', 'Domains & email']

const steps = [
  ['01', 'Make yourself at home', 'Create your account and name your business. Start with a blank site or choose a template.'],
  ['02', 'Make it feel like you', 'Use AI to help draft your pages. Add your products, services or classes, and give it your own look.'],
  ['03', 'Open your doors online', 'Publish your site, connect payments when you’re ready to sell, and share it with your customers.'],
]

const NAV = [
  { label: 'Features', href: '#features' },
  { label: 'Pricing', href: '#pricing' },
  { label: 'FAQ', href: '#faq' },
]

const MOBILE_LINK = 'rounded-xl px-3 py-2.5 font-medium text-[#deded4] hover:bg-white/5'

function Header() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const solid = scrolled || open
  return (
    <header className={`sticky top-0 z-30 border-b transition-colors ${solid ? 'border-white/10 bg-[#141c14]/95 backdrop-blur-xl' : 'border-transparent'}`}>
      <div className={`flex items-center justify-between py-4 ${WRAP}`}>
        <Link to="/gummfit" className="flex items-center gap-2.5" aria-label="Gummfit home">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72] text-sm font-black tracking-tighter text-[#182115] shadow-[0_0_25px_rgba(212,255,114,0.25)]">G</span>
          <span className="text-lg font-semibold tracking-[-0.04em]">Gummfit</span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm md:flex" aria-label="Main">
          {NAV.map((item) => <a key={item.href} href={item.href} className="font-medium text-[#c5c8bc] transition hover:text-white">{item.label}</a>)}
          <Link to="/gummfit/discover" className="font-medium text-[#c5c8bc] transition hover:text-white">Discover</Link>
          <Link to="/gummfit/creators" className="font-medium text-[#c5c8bc] transition hover:text-white">Creators</Link>
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <Link to="/gummfit/login" className="hidden font-medium text-[#deded4] transition hover:text-white sm:block">Sign in</Link>
          <Link to={SIGNUP_PATH} className="rounded-full bg-[#d4ff72] px-4 py-2 font-semibold text-[#182115] transition hover:-translate-y-0.5 hover:bg-[#e2ff9a] sm:px-5">Get started</Link>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-white/15 text-[#deded4] md:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>
      {open && (
        <nav className={`flex flex-col gap-1 pb-5 text-base md:hidden ${WRAP}`} aria-label="Mobile">
          {NAV.map((item) => <a key={item.href} href={item.href} onClick={() => setOpen(false)} className={MOBILE_LINK}>{item.label}</a>)}
          <Link to="/gummfit/discover" className={MOBILE_LINK}>Discover</Link>
          <Link to="/gummfit/creators" className={MOBILE_LINK}>Creators</Link>
          <Link to="/gummfit/login" className={MOBILE_LINK}>Sign in</Link>
        </nav>
      )}
    </header>
  )
}

function InHouseStrip() {
  return (
    <section className="relative z-10 border-y border-white/10 bg-[#1a201a]">
      <div className={`flex flex-col gap-4 py-6 lg:flex-row lg:items-center lg:gap-10 ${WRAP}`}>
        <p className={`${EYEBROW} shrink-0 text-[#d4ff72]`}>Built by one team. Made to work together.</p>
        <ul className="flex flex-wrap gap-2">
          {IN_HOUSE.map((item) => <li key={item} className="rounded-full border border-white/10 px-3 py-1.5 text-xs font-medium text-[#d8d9d0]">{item}</li>)}
        </ul>
      </div>
    </section>
  )
}

function HowItWorks() {
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()
  return (
    <section className={`grid gap-14 py-24 sm:py-32 lg:grid-cols-[0.84fr_1.16fr] lg:gap-20 ${WRAP}`}>
      <div>
        <p className={`${EYEBROW} text-[#d4ff72]`}>How it works</p>
        <h2 className="mt-5 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] text-[#f8f7f0] sm:text-5xl">Your next chapter starts here.</h2>
        <p className="mt-6 max-w-md text-lg leading-8 text-[#afb3a7]">Start small. Make it yours. Add more as your business grows.</p>
        <Link to={SIGNUP_PATH} className="mt-8 inline-flex items-center gap-2 font-semibold text-[#d4ff72] transition hover:text-[#e2ff9a]">Start with your business <ArrowRight className="h-4 w-4" /></Link>
      </div>
      <div ref={attachReveal} className={`border-t border-white/10 ${revealClass}`}>
        {steps.map(([number, title, body]) => (
          <div key={number} className="group grid grid-cols-[3rem_1fr_auto] gap-3 border-b border-white/10 py-7 sm:grid-cols-[5rem_1fr_auto] sm:py-9">
            <span className="text-sm font-bold text-[#d4ff72]">{number}</span>
            <div>
              <h3 className="text-2xl font-semibold tracking-[-0.04em] text-[#f3f1e7]">{title}</h3>
              <p className="mt-2 max-w-lg text-sm leading-6 text-[#afb3a7]">{body}</p>
            </div>
            <ArrowUpRight className="mt-1 h-5 w-5 text-[#8a8f82] motion-safe:transition-transform motion-safe:duration-300 group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-[#d4ff72]" />
          </div>
        ))}
      </div>
    </section>
  )
}

function DiscoverStrip() {
  const [entries, setEntries] = useState<CappeDirectoryEntry[]>([])

  useEffect(() => {
    fetchCappeDirectory({ limit: 3, sort: 'newest' }).then((page) => setEntries(page.entries)).catch(() => setEntries([]))
  }, [])

  if (!entries.length) return null
  return (
    <section className="border-y border-white/10 bg-[#1a201a] py-20 sm:py-24">
      <div className={WRAP}>
        <div className="flex flex-wrap items-end justify-between gap-5"><div><p className={`${EYEBROW} text-[#d4ff72]`}>Built with Gummfit</p><h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[#f5f3eb] sm:text-4xl">Small businesses, open for business.</h2></div><Link to="/gummfit/discover" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#deded4] hover:text-[#d4ff72]">Discover more <ArrowRight className="h-4 w-4" /></Link></div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">{entries.map((entry) => <DirectoryCard key={entry.slug} entry={entry} />)}</div>
      </div>
    </section>
  )
}

export default function CappeLanding() {
  const pricing = usePublicPricing()

  return (
    <main className="relative min-h-screen overflow-x-clip bg-[#141c14] text-[#f5f3eb] selection:bg-[#d4ff72] selection:text-[#172013]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[52rem] bg-[radial-gradient(ellipse_at_85%_30%,rgba(173,199,114,0.10),transparent_60%)]" />

      <Header />
      <Hero />
      <InHouseStrip />
      <Features />
      <StackComparison />
      <Pricing pricing={pricing} />
      <HowItWorks />
      <DiscoverStrip />
      <Faq />

      <section className="relative overflow-hidden border-t border-white/10 py-28 text-center sm:py-36">
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-80 w-80 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#d4ff72]/12 blur-3xl" />
        <div className={`relative ${WRAP}`}>
          <h2 className="mx-auto max-w-3xl text-4xl font-semibold leading-[0.96] tracking-[-0.07em] text-[#f8f7f0] sm:text-6xl">You bring the business.<br /><span className="font-serif italic text-[#d4ff72]">We’ll bring the tools.</span></h2>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-[#afb3a7]">Make a home for your ideas, your products, and your next customer.</p>
          <Link to={SIGNUP_PATH} className={`mt-9 ${LIME_BUTTON}`}>Build your website <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </section>

      <footer className="border-t border-white/10 py-7">
        <div className={`flex flex-col justify-between gap-3 text-xs text-[#969b8e] sm:flex-row ${WRAP}`}>
          <span>© {new Date().getFullYear()} Gummfit</span>
          <div className="flex flex-wrap gap-5">
            <a href="#pricing" className="hover:text-white">Pricing</a>
            <Link to="/gummfit/discover" className="hover:text-white">Discover</Link>
            <Link to="/gummfit/creators" className="hover:text-white">Gummfit Creators</Link>
            <Link to="/gummfit/login" className="hover:text-white">Sign in</Link>
            <span className="uppercase tracking-[0.16em]">A Matcha product</span>
          </div>
        </div>
      </footer>
    </main>
  )
}
