import type { ReactNode } from 'react'
import { ArrowUpRight, CalendarDays, Check, Globe, Mail, MessageSquareText, ShoppingBag, Sparkles, Star } from 'lucide-react'
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

const tiles: Tile[] = [
  {
    icon: Sparkles,
    eyebrow: 'Your website',
    title: 'From “I have an idea” to “that’s my business.”',
    body: 'Get a head start with AI, then make the words, colors and layout your own in the visual editor.',
    className: 'md:col-span-2 bg-[#dceba8] text-[#26321e]',
    vignette: (
      <div aria-hidden="true" className="mt-7 grid gap-3 sm:grid-cols-[1fr_0.9fr]">
        <div className="self-start rounded-xl border border-[#26321e]/15 bg-[#eff5d8] px-4 py-3 text-xs leading-5"><Sparkles className="mb-2 h-4 w-4" />“A neighborhood bakery. Warm colors, fresh bread, and room for Saturday classes.”</div>
        <div className="rounded-xl bg-[#f7f4eb] p-3 shadow-[0_6px_20px_rgba(38,50,30,0.08)]">
          <div className="flex items-center justify-between border-b border-[#26321e]/10 pb-2"><span className="font-serif text-sm">Sunday Bread</span><span className="flex gap-1"><span className="h-1 w-5 rounded bg-[#26321e]/20" /><span className="h-1 w-5 rounded bg-[#26321e]/20" /></span></div>
          <div className="mt-2 flex items-center justify-between rounded bg-[#ecd7bd] px-3 py-4"><p className="font-serif text-lg leading-5">Something<br /><i>good is rising.</i></p><span className="h-12 w-9 rotate-12 rounded-t-full bg-[#bb8454] shadow-[-5px_2px_0_#d3a67a]" /></div>
          <div className="mt-2 flex items-center gap-1 text-[9px] text-[#647448]"><Check className="h-2.5 w-2.5" /> Ready for your finishing touches</div>
        </div>
      </div>
    ),
  },
  {
    icon: ShoppingBag,
    eyebrow: 'Your shop',
    title: 'Good things deserve a great storefront.',
    body: 'Sell products, downloads or services. Manage stock, discounts and orders alongside your site.',
    className: 'bg-[#eed8bf] text-[#402f21]',
    vignette: <div aria-hidden="true" className="mt-7 flex items-center gap-3 rounded-xl border border-[#402f21]/10 bg-white/25 px-4 py-3"><span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#d0b08e]"><ShoppingBag className="h-4 w-4" /></span><div className="flex-1"><p className="text-xs font-semibold">One more happy customer.</p><p className="mt-1 text-[10px] opacity-70">Order received · Ready to pack</p></div><Check className="h-4 w-4" /></div>,
  },
  {
    icon: CalendarDays,
    eyebrow: 'Your bookings',
    title: 'Make time for what you do best.',
    body: 'Appointments and classes, with availability, reminders and a place for customers to book.',
    className: 'bg-[#c7b9dc] text-[#352a40]',
    vignette: <div aria-hidden="true" className="mt-7 rounded-xl border border-[#352a40]/10 bg-white/20 p-3"><div className="flex items-center justify-between text-[10px] font-semibold"><span>Saturday classes</span><CalendarDays className="h-3.5 w-3.5" /></div><div className="mt-3 flex gap-2">{['10:00 AM', '12:00 PM', '2:00 PM'].map((time, i) => <span key={time} className={`flex-1 rounded-md px-1 py-2 text-center text-[9px] ${i === 0 ? 'bg-[#352a40] text-[#f2edf8]' : 'border border-[#352a40]/15'}`}>{time}</span>)}</div></div>,
  },
  {
    icon: Globe,
    eyebrow: 'Your address',
    title: 'A little more official. A lot more you.',
    body: 'Connect a domain you own or register a new one. Add business email when you need it.',
    className: 'md:col-span-2 bg-[#27332a] text-[#f3f1e7] border border-white/10',
    vignette: <div aria-hidden="true" className="mt-7 grid gap-2 text-xs sm:grid-cols-2"><div className="flex min-w-0 items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3"><Globe className="h-4 w-4 shrink-0 text-[#d4ff72]" /><span className="min-w-0 truncate">yourbusiness.example.com</span><Check className="ml-auto h-3.5 w-3.5 shrink-0 text-[#d4ff72]" /></div><div className="flex min-w-0 items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3"><Mail className="h-4 w-4 shrink-0 text-[#d4ff72]" /><span className="min-w-0 truncate">hello@yourbusiness.example.com</span></div></div>,
  },
  {
    icon: Mail,
    eyebrow: 'Your audience',
    title: 'Give them a reason to come back.',
    body: 'Collect subscribers with forms and share your next launch, offer or opening with a newsletter.',
    className: 'bg-[#1b241c] text-[#f3f1e7] border border-white/10',
  },
  {
    icon: Star,
    eyebrow: 'Your story',
    title: 'Let your work speak for itself.',
    body: 'Publish a blog, collect reviews, and help new customers get to know your business.',
    className: 'bg-[#1b241c] text-[#f3f1e7] border border-white/10',
  },
  {
    icon: MessageSquareText,
    eyebrow: 'Your customers',
    title: 'Keep the conversation going.',
    body: 'Manage customer details and messages in the same place you run your site.',
    className: 'bg-[#1b241c] text-[#f3f1e7] border border-white/10',
  },
]

export default function Features() {
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()
  return (
    <section id="features" className={`scroll-mt-24 py-20 sm:py-28 ${WRAP}`}>
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end lg:gap-16">
        <div className="max-w-xl"><p className={`${EYEBROW} text-[#d4ff72]`}>One home for your business</p><h2 className="mt-4 text-4xl font-medium leading-[1.04] tracking-[-0.055em] text-[#f8f7f0] sm:text-5xl">All the pieces.<br /><span className="font-serif italic text-[#d4ff72]">Already together.</span></h2></div>
        <p className="max-w-sm text-base leading-7 text-[#afb8a4]">Build your presence, take orders, and stay in touch. Gummfit makes the tools, so you can focus on making your business.</p>
      </div>
      <div ref={attachReveal} className={`mt-10 grid gap-3 md:grid-cols-3 ${revealClass}`}>
        {tiles.map(({ icon: Icon, eyebrow, title, body, className, vignette }) => (
          <article key={eyebrow} className={`flex flex-col rounded-2xl p-6 sm:p-7 ${className}`}>
            <div className="flex items-center justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-full border border-current/15"><Icon className="h-4 w-4" strokeWidth={1.6} /></span><ArrowUpRight aria-hidden="true" className="h-4 w-4 opacity-35" /></div>
            <p className="mt-6 text-[10px] font-semibold uppercase tracking-[0.18em] opacity-70">{eyebrow}</p>
            <h3 className="mt-3 max-w-md text-[1.55rem] font-medium leading-[1.12] tracking-[-0.04em]">{title}</h3>
            <p className="mt-3 max-w-md text-sm leading-6 opacity-80">{body}</p>
            {vignette}
          </article>
        ))}
      </div>
    </section>
  )
}
