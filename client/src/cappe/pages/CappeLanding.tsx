import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  CalendarDays,
  Check,
  CircleDollarSign,
  CreditCard,
  Sparkles,
  UsersRound,
} from 'lucide-react'
import { fetchCappeDirectory } from '../api'
import DirectoryCard from '../components/DirectoryCard'
import type { CappeDirectoryEntry } from '../types'

const WRAP = 'mx-auto max-w-7xl px-5 sm:px-8 lg:px-12'

const systems = [
  {
    icon: Sparkles,
    eyebrow: 'AI site studio',
    title: 'A site with your sensibility, not somebody else’s template.',
    body: 'Start with an intelligent first draft, then direct every word, photo, service and detail.',
    className: 'md:col-span-2 bg-[#dceba8] text-[#182115]',
  },
  {
    icon: CalendarDays,
    eyebrow: 'Scheduling',
    title: 'A calendar your guests love to use.',
    body: 'Classes, appointments, capacity and availability—always in step.',
    className: 'bg-[#c7b9dc] text-[#251e2b]',
  },
  {
    icon: CreditCard,
    eyebrow: 'Payments',
    title: 'The moment they book is the moment they pay.',
    body: 'Take payments, sell packages, and keep revenue attached to the service.',
    className: 'bg-[#eed8bf] text-[#302318]',
  },
  {
    icon: UsersRound,
    eyebrow: 'Guest care',
    title: 'Know who is walking through the door.',
    body: 'Intake, client history and every conversation live alongside the day’s work.',
    className: 'md:col-span-2 bg-[#293229] text-[#f3f1e7]',
  },
]

const journey = [
  ['01', 'Be discovered', 'A distinctive home for your business, built to turn interest into action.'],
  ['02', 'Fill the calendar', 'Let guests choose a class or appointment, complete their intake, and pay in one clear flow.'],
  ['03', 'Make them regulars', 'Keep the relationship moving with thoughtful notes, campaigns and a complete guest picture.'],
]

function StudioConsole() {
  const bookings = [
    { time: '8:00', title: 'Reformer flow', guest: 'Maya R.', tone: 'bg-[#d9f192]' },
    { time: '9:15', title: 'Private session', guest: 'Jules B.', tone: 'bg-[#e5d1bb]' },
    { time: '10:30', title: 'Strength + stretch', guest: '12 guests', tone: 'bg-[#c7b9dc]' },
  ]

  return (
    <div className="relative mx-auto w-full max-w-xl">
      <div className="pointer-events-none absolute -inset-12 rounded-full bg-[#d4ff72]/15 blur-3xl" />
      <div className="relative rotate-[2deg] rounded-[1.8rem] border border-white/20 bg-[#f3f0e6] p-3 shadow-[0_35px_100px_rgba(0,0,0,0.36)] transition duration-500 hover:rotate-0 sm:p-4">
        <div className="overflow-hidden rounded-[1.3rem] bg-[#e1dacd] text-[#20251f]">
          <div className="flex items-center justify-between border-b border-[#c7c3b8] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#74766e] sm:px-5">
            <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#a9ca48]" /> Today at Lune</span>
            <span>Tuesday, 14 May</span>
          </div>
          <div className="grid sm:grid-cols-[0.78fr_1.22fr]">
            <div className="border-b border-[#c7c3b8] bg-[#272f27] p-5 text-[#f6f4eb] sm:border-b-0 sm:border-r sm:p-6">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#d4ff72]">Lune Pilates</p>
              <h3 className="mt-5 text-3xl font-semibold leading-[0.92] tracking-[-0.07em]">A good day<br />takes shape.</h3>
              <div className="mt-9 flex gap-2"><span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-medium">18 bookings</span><span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-medium">$1,240 today</span></div>
              <div className="mt-8 border-t border-white/10 pt-4 text-xs leading-5 text-[#b9bcb2]">Your site, schedule, payments and guest notes—one calm place to start the day.</div>
            </div>
            <div className="p-4 sm:p-5">
              <div className="mb-3 flex items-center justify-between"><p className="text-xs font-bold">Today’s schedule</p><button className="rounded-full bg-[#293229] px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-[#e6f4b3]">Open calendar</button></div>
              <div className="space-y-2">{bookings.map((booking) => <div key={booking.time} className="flex items-center gap-2 rounded-xl bg-[#f8f6ef] p-2.5 shadow-sm"><span className="w-8 text-[10px] font-bold text-[#777970]">{booking.time}</span><span className={`h-8 w-1 rounded-full ${booking.tone}`} /><div className="min-w-0 flex-1"><p className="truncate text-[11px] font-bold">{booking.title}</p><p className="mt-0.5 text-[10px] text-[#7b7d74]">{booking.guest}</p></div><ArrowUpRight className="h-3.5 w-3.5 text-[#85887e]" /></div>)}</div>
              <div className="mt-3 flex items-center gap-2 rounded-xl border border-dashed border-[#b6b4a9] p-2.5 text-[10px] text-[#76786f]"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#e8eccd] text-[#596d24]">+</span> Add a walk-in or appointment</div>
            </div>
          </div>
        </div>
      </div>
      <div className="absolute -bottom-7 -left-3 rounded-2xl border border-white/10 bg-[#2a342a] px-4 py-3 text-[#f6f4eb] shadow-xl sm:-left-8"><div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#d4ff72] text-[#263219]"><CircleDollarSign className="h-4 w-4" /></span><div><p className="text-xs font-semibold">Payment received</p><p className="mt-0.5 text-[10px] text-[#b3bbac]">Intro pack · $120.00</p></div></div></div>
    </div>
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
        <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#d4ff72]">Built with Gummfit</p><h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[#f5f3eb] sm:text-4xl">Businesses with a better front door.</h2></div><Link to="/gummfit/discover" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#deded4] hover:text-[#d4ff72]">Discover more <ArrowRight className="h-4 w-4" /></Link></div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">{entries.map((entry) => <DirectoryCard key={entry.slug} entry={entry} />)}</div>
      </div>
    </section>
  )
}

export default function CappeLanding() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-[#111510] text-[#f5f3eb] selection:bg-[#d4ff72] selection:text-[#172013]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[50rem] bg-[radial-gradient(circle_at_82%_14%,rgba(211,255,108,0.16),transparent_24rem),radial-gradient(circle_at_12%_38%,rgba(195,176,222,0.14),transparent_23rem)]" />

      <header className={`relative z-10 flex items-center justify-between py-5 ${WRAP}`}>
        <Link to="/gummfit" className="flex items-center gap-2.5" aria-label="Gummfit home"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72] text-sm font-black tracking-tighter text-[#182115] shadow-[0_0_25px_rgba(212,255,114,0.25)]">G</span><span className="text-lg font-semibold tracking-[-0.04em]">Gummfit</span></Link>
        <nav className="flex items-center gap-3 text-sm sm:gap-5"><Link to="/gummfit/creators" className="hidden font-medium text-[#c5c8bc] transition hover:text-white md:block">Creators</Link><Link to="/gummfit/discover" className="hidden font-medium text-[#c5c8bc] transition hover:text-white sm:block">Discover</Link><Link to="/gummfit/login" className="font-medium text-[#deded4] transition hover:text-white">Sign in</Link><Link to="/gummfit/website-setup" className="rounded-full bg-[#d4ff72] px-4 py-2 font-semibold text-[#182115] transition hover:-translate-y-0.5 hover:bg-[#e2ff9a] sm:px-5">Get started</Link></nav>
      </header>

      <section className={`relative z-10 grid items-center gap-14 pb-24 pt-14 sm:pb-32 sm:pt-20 lg:grid-cols-[0.96fr_1.04fr] lg:gap-16 ${WRAP}`}>
        <div className="max-w-2xl"><div className="inline-flex items-center gap-2 rounded-full border border-[#d4ff72]/25 bg-[#d4ff72]/10 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[#dcff91]"><Sparkles className="h-3.5 w-3.5" /> The service business operating system</div><h1 className="mt-7 text-[3.4rem] font-semibold leading-[0.92] tracking-[-0.075em] text-[#fbfaf4] sm:text-6xl lg:text-7xl">Your business,<br /><span className="text-[#d4ff72]">beautifully</span> in motion.</h1><p className="mt-7 max-w-xl text-lg leading-8 text-[#b9bcb0] sm:text-xl">Gummfit gives studios, salons and service teams one place to build their site, fill the schedule, take payment, and take care of every guest.</p><div className="mt-9 flex flex-col gap-3 sm:flex-row"><Link to="/gummfit/website-setup" className="inline-flex items-center justify-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#182115] transition hover:-translate-y-0.5 hover:bg-[#e2ff9a]">Build your Gummfit <ArrowRight className="h-4 w-4" /></Link><a href="#system" className="inline-flex items-center justify-center gap-2 px-4 py-3 text-sm font-semibold text-[#e1e2d9] transition hover:text-[#d4ff72]">See what’s included <ArrowDown /></a></div><div className="mt-11 flex flex-wrap gap-5 text-xs font-medium text-[#a7ac9d]"><span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-[#d4ff72]" /> No code required</span><span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-[#d4ff72]" /> Built for teams</span><span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-[#d4ff72]" /> Start with AI</span></div></div>
        <StudioConsole />
      </section>

      <section className="relative z-10 border-y border-white/10 bg-[#1a201a]"><div className={`${WRAP} grid gap-px overflow-hidden bg-white/10 sm:grid-cols-4`}><div className="bg-[#1a201a] px-5 py-5 text-xs font-semibold uppercase tracking-[0.16em] text-[#d4ff72]">One connected experience</div>{['Website + AI', 'Scheduling + payments', 'Guests + follow-up'].map((item) => <div key={item} className="bg-[#1a201a] px-5 py-5 text-sm font-medium text-[#d8d9d0]">{item}</div>)}</div></section>

      <section id="system" className={`py-24 sm:py-32 ${WRAP}`}><div className="max-w-2xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#d4ff72]">More than a beautiful website</p><h2 className="mt-4 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] text-[#f8f7f0] sm:text-5xl">A calmer way to run the day.</h2><p className="mt-5 text-lg leading-8 text-[#afb3a7]">The tools your business needs should feel like one system, not a stack of tabs your team has to keep translating between.</p></div><div className="mt-14 grid gap-3 md:grid-cols-3">{systems.map(({ icon: Icon, eyebrow, title, body, className }, index) => <article key={eyebrow} className={`min-h-72 rounded-[1.6rem] p-6 sm:p-7 ${className}`}><div className="flex items-start justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-black/10"><Icon className="h-5 w-5" /></span><span className="text-xs font-bold tracking-[0.18em] opacity-50">0{index + 1}</span></div><p className="mt-12 text-xs font-bold uppercase tracking-[0.15em] opacity-60">{eyebrow}</p><h3 className="mt-3 max-w-md text-2xl font-semibold leading-[1.02] tracking-[-0.045em]">{title}</h3><p className="mt-4 max-w-md text-sm leading-6 opacity-75">{body}</p></article>)}</div></section>

      <section className="bg-[#e8e1d2] py-24 text-[#20261e] sm:py-32"><div className={`grid gap-14 lg:grid-cols-[0.84fr_1.16fr] lg:gap-20 ${WRAP}`}><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#647c28]">Designed around your guests</p><h2 className="mt-5 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] sm:text-5xl">A better experience is good business.</h2><p className="mt-6 max-w-md text-lg leading-8 text-[#5c6256]">From the first Google search to the next appointment, Gummfit helps every interaction feel like your business at its best.</p><Link to="/gummfit/website-setup" className="mt-8 inline-flex items-center gap-2 font-semibold text-[#4f6820] transition hover:text-[#172013]">Start with your business <ArrowRight className="h-4 w-4" /></Link></div><div className="space-y-0 border-t border-[#bdb8aa]">{journey.map(([number, title, body]) => <div key={number} className="group grid grid-cols-[3.5rem_1fr_auto] gap-3 border-b border-[#bdb8aa] py-7 sm:grid-cols-[5rem_1fr_auto] sm:py-9"><span className="text-sm font-bold text-[#698028]">{number}</span><div><h3 className="text-2xl font-semibold tracking-[-0.04em]">{title}</h3><p className="mt-2 max-w-lg text-sm leading-6 text-[#5e6459]">{body}</p></div><ArrowUpRight className="mt-1 h-5 w-5 transition-transform duration-300 group-hover:-translate-y-1 group-hover:translate-x-1" /></div>)}</div></div></section>

      <DiscoverStrip />

      <section className="relative overflow-hidden py-28 text-center sm:py-36"><div className="pointer-events-none absolute left-1/2 top-1/2 h-80 w-80 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#d4ff72]/12 blur-3xl" /><div className={`relative ${WRAP}`}><BadgeCheck className="mx-auto h-7 w-7 text-[#d4ff72]" /><h2 className="mx-auto mt-5 max-w-3xl text-4xl font-semibold leading-[0.96] tracking-[-0.07em] text-[#f8f7f0] sm:text-6xl">Your business is personal.<br /><span className="text-[#d4ff72]">Your system should be, too.</span></h2><p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-[#afb3a7]">Create the place your guests will find, book, and remember.</p><Link to="/gummfit/website-setup" className="mt-9 inline-flex items-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#182115] transition hover:-translate-y-0.5 hover:bg-[#e2ff9a]">Get started with Gummfit <ArrowRight className="h-4 w-4" /></Link></div></section>

      <footer className="border-t border-white/10 py-7"><div className={`flex flex-col justify-between gap-3 text-xs text-[#969b8e] sm:flex-row ${WRAP}`}><span>© {new Date().getFullYear()} Gummfit</span><div className="flex gap-5"><Link to="/gummfit/creators" className="hover:text-white">Gummfit Creators</Link><Link to="/gummfit/login" className="hover:text-white">Sign in</Link><span className="uppercase tracking-[0.16em]">A Matcha product</span></div></div></footer>
    </main>
  )
}

function ArrowDown() {
  return <span aria-hidden="true" className="text-lg leading-none">↓</span>
}
