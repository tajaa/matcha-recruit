import type { ReactNode } from 'react'
import { CalendarDays, Globe, Mail, MessageSquareText, ShoppingBag, Sparkles, Star } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { EYEBROW, WRAP, useReveal } from './shared'

type Tile = {
  icon: LucideIcon
  eyebrow: string
  title: string
  body: string
  className: string
  vignette?: ReactNode
}

// Every tile maps to a module that ships today (client/src/cappe/routes.tsx).
// Don't add one for something we'd have to buy from a vendor — that's the pitch.
const tiles: Tile[] = [
  {
    icon: Sparkles,
    eyebrow: 'AI site builder',
    title: 'Describe your business. Get a real first draft.',
    body: 'Our AI drafts the pages, copy and layout. You direct every word, photo and detail from there.',
    className: 'md:col-span-2 bg-[#dceba8] text-[#182115]',
    vignette: (
      <div className="mt-6 space-y-2 text-[11px]">
        <p className="w-fit max-w-[85%] rounded-2xl rounded-bl-sm bg-[#182115]/10 px-3 py-2">A cozy bakery in Portland — we sell bread, take cake orders, and run Saturday classes.</p>
        <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-[#182115] px-3 py-2 text-[#e6f4b3]">Here’s a first draft: Home, Shop, Cakes, Classes and Contact. ✓</p>
      </div>
    ),
  },
  {
    icon: ShoppingBag,
    eyebrow: 'Online store',
    title: 'Sell anything you make.',
    body: 'Physical goods, digital downloads and subscriptions — with shipping, tax, discounts and stock built in.',
    className: 'bg-[#eed8bf] text-[#302318]',
  },
  {
    icon: CalendarDays,
    eyebrow: 'Bookings',
    title: 'Appointments and classes that pay up front.',
    body: 'Availability, capacity, reminders and self-serve rescheduling.',
    className: 'bg-[#c7b9dc] text-[#251e2b]',
  },
  {
    icon: Globe,
    eyebrow: 'Domain + email',
    title: 'yourname.com, and you@yourname.com.',
    body: 'Register or connect a domain, and add private mailboxes on it — no separate registrar or email host.',
    className: 'md:col-span-2 bg-[#293229] text-[#f3f1e7]',
    vignette: (
      <div className="mt-6 flex flex-wrap gap-2 text-[11px] font-semibold">
        <span className="rounded-full bg-white/10 px-3 py-1.5">yourbusiness.com · Connected</span>
        <span className="rounded-full bg-[#d4ff72] px-3 py-1.5 text-[#182115]">hello@yourbusiness.com</span>
      </div>
    ),
  },
  {
    icon: Mail,
    eyebrow: 'Newsletters + forms',
    title: 'Grow a list. Send the news.',
    body: 'Signup forms, campaigns and subscribers live with your site, not in another tool.',
    className: 'bg-[#1f2720] text-[#f3f1e7] border border-white/10',
  },
  {
    icon: Star,
    eyebrow: 'Reviews + blog',
    title: 'Get found, get trusted.',
    body: 'Collect reviews and publish posts that help you show up in search.',
    className: 'bg-[#1f2720] text-[#f3f1e7] border border-white/10',
  },
  {
    icon: MessageSquareText,
    eyebrow: 'Clients + messages',
    title: 'Every customer, in one place.',
    body: 'Order history, bookings and conversations together, so nothing falls through.',
    className: 'bg-[#1f2720] text-[#f3f1e7] border border-white/10',
  },
]

export default function Features() {
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()
  return (
    <section id="features" className={`scroll-mt-24 py-24 sm:py-32 ${WRAP}`}>
      <div className="max-w-2xl">
        <p className={`${EYEBROW} text-[#d4ff72]`}>Everything, built by us</p>
        <h2 className="mt-4 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] text-[#f8f7f0] sm:text-5xl">One system, not a stack of subscriptions.</h2>
        <p className="mt-5 text-lg leading-8 text-[#afb3a7]">Most small businesses glue together five or six tools. Every part of Gummfit is made by the same team, so it works together out of the box.</p>
      </div>
      <div ref={attachReveal} className={`mt-14 grid gap-3 md:grid-cols-3 ${revealClass}`}>
        {tiles.map(({ icon: Icon, eyebrow, title, body, className, vignette }) => (
          <article key={eyebrow} className={`flex min-h-64 flex-col rounded-[1.6rem] p-6 motion-safe:transition motion-safe:duration-300 hover:-translate-y-1 sm:p-7 ${className}`}>
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-black/10"><Icon className="h-5 w-5" /></span>
            <p className="mt-8 text-xs font-bold uppercase tracking-[0.15em] opacity-60">{eyebrow}</p>
            <h3 className="mt-3 max-w-md text-2xl font-semibold leading-[1.04] tracking-[-0.045em]">{title}</h3>
            <p className="mt-3 max-w-md text-sm leading-6 opacity-75">{body}</p>
            {vignette}
          </article>
        ))}
      </div>
    </section>
  )
}
