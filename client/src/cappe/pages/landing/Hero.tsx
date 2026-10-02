import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, Check, Coffee, Lock, ShoppingBag } from 'lucide-react'
import { LIME_BUTTON, SIGNUP_PATH, WRAP } from './shared'

/** Lightweight vector artwork keeps the example storefront crisp at any size. */
function CoffeeBag({ light = false }: { light?: boolean }) {
  return (
    <svg viewBox="0 0 160 190" className="h-full w-full overflow-visible" fill="none" aria-hidden="true">
      <ellipse cx="80" cy="177" rx="46" ry="8" fill="#33291e" opacity="0.12" />
      <path d="M43 18h74l7 19-5 132H41L36 37l7-19Z" fill={light ? '#e6d4b6' : '#3b4937'} />
      <path d="M43 18h74l-3 10H46l-3-10Z" fill={light ? '#c7ac86' : '#263221'} />
      <path d="m36 37 9 7-4 125-5-132Zm88 0-9 7 4 125 5-132Z" fill="#111b10" opacity="0.13" />
      <path d="M46 43h68v106H46z" fill={light ? '#eeb89c' : '#e5e7c1'} />
      <path d="m80 57 4 10 10 4-10 4-4 10-4-10-10-4 10-4 4-10Z" fill="#37452f" />
      <text x="80" y="105" textAnchor="middle" fill="#37452f" fontFamily="Georgia, serif" fontSize="18">ridgeline</text>
      <text x="80" y="121" textAnchor="middle" fill="#37452f" fontFamily="sans-serif" fontSize="6" letterSpacing="2">COFFEE ROASTERS</text>
      <path d="M59 132h42" stroke="#37452f" opacity="0.4" />
      <text x="80" y="142" textAnchor="middle" fill="#37452f" fontFamily="sans-serif" fontSize="6">SMALL BATCH · 12 OZ</text>
      <path d="M47 158h66" stroke={light ? '#b99f7b' : '#79856c'} />
    </svg>
  )
}

/** Illustrative storefront, rather than customer evidence or a live demo. */
function BrowserMockup() {
  return (
    <div className="mx-auto w-full max-w-[36rem]">
      <div className="relative pb-6 pt-5 lg:pt-0">
        <div aria-hidden="true" className="pointer-events-none absolute -inset-6 rounded-full bg-[#d4ff72]/8 blur-3xl" />
        <div aria-hidden="true" className="relative overflow-hidden rounded-[1.2rem] border border-[#ece9db]/25 bg-[#f5f1e7] shadow-[0_30px_90px_rgba(0,0,0,0.35)] lg:rotate-[2deg]">
          <div className="flex items-center gap-1.5 border-b border-[#ded9cb] bg-[#eae6da] px-4 py-3">
            <span className="h-2 w-2 rounded-full bg-[#bcbaa9]" /><span className="h-2 w-2 rounded-full bg-[#bcbaa9]" /><span className="h-2 w-2 rounded-full bg-[#bcbaa9]" />
            <span className="mx-auto flex items-center gap-1.5 text-[10px] text-[#717464]"><Lock className="h-2.5 w-2.5" /> ridgeline.example.com</span>
            <ArrowUpRight className="h-3 w-3 text-[#717464]" />
          </div>
          <div className="px-5 pb-5 pt-4 text-[#34402e] sm:px-7 sm:pb-7">
            <div className="flex items-center justify-between border-b border-[#34402e]/15 pb-4">
              <span className="flex items-center gap-1.5 font-serif text-xl tracking-tight"><Coffee className="h-5 w-5" strokeWidth={1.5} /> ridgeline</span>
              <span className="flex items-center gap-4 text-[9px] font-medium"><span>Our coffee</span><span>Visit us</span><ShoppingBag className="h-3.5 w-3.5" /></span>
            </div>
            <div className="relative mt-5 overflow-hidden rounded-sm bg-[#dedfc5] px-5 py-7 sm:px-6">
              <div className="relative z-10 max-w-[60%]">
                <p className="text-[8px] font-semibold uppercase tracking-[0.2em]">Good mornings start here.</p>
                <p className="mt-3 font-serif text-[1.9rem] leading-[0.98] tracking-[-0.055em] sm:text-[2.65rem]">A little ritual.<br />A better day.</p>
                <p className="mt-3 max-w-40 text-[9px] leading-4 text-[#59614a]">Thoughtfully roasted coffee,<br />from our neighborhood to yours.</p>
                <span className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#34402e] px-3 py-2 text-[9px] font-medium text-[#f5f1e7]">Find your blend <ArrowRight className="h-2.5 w-2.5" /></span>
              </div>
              <div className="absolute -right-1 bottom-1 h-[92%] w-[48%] rotate-[9deg]"><CoffeeBag /></div>
            </div>
            <div className="mt-5 flex items-baseline justify-between"><p className="font-serif text-lg tracking-tight">Meet your morning favorites.</p><span className="text-[8px] underline underline-offset-2">Shop all</span></div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {[{ name: 'The everyday blend', price: '$18', light: false }, { name: 'A brighter morning', price: '$22', light: true }].map((product) => (
                <div key={product.name}>
                  <div className={`flex h-28 justify-center rounded-sm sm:h-36 ${product.light ? 'bg-[#e7d9cb]' : 'bg-[#e2e5d6]'}`}><div className="h-full w-28 py-1"><CoffeeBag light={product.light} /></div></div>
                  <div className="mt-2 flex justify-between gap-2 text-[9px] font-medium"><span>{product.name}</span><span>{product.price}</span></div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div aria-hidden="true" className="absolute -bottom-1 left-2 flex items-center gap-3 rounded-xl border border-white/15 bg-[#f6f3e9] px-4 py-3 text-[#293229] shadow-[0_12px_40px_rgba(0,0,0,0.22)] sm:-left-5">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72]"><Check className="h-4 w-4" /></span>
          <div><p className="text-xs font-semibold">Your shop is open.</p><p className="mt-0.5 text-[10px] text-[#68705f]">New order · $40.00 paid</p></div>
        </div>
        <div aria-hidden="true" className="absolute -right-3 top-16 hidden items-center gap-2.5 rounded-xl border border-white/10 bg-[#c7b9dc] px-3.5 py-3 text-[#302638] shadow-lg sm:flex">
          <CalendarDays className="h-5 w-5" strokeWidth={1.5} /><div><p className="text-[10px] font-semibold">Coffee tasting</p><p className="mt-0.5 text-[9px]">Saturday · 10:00 AM</p></div>
        </div>
      </div>
      <p className="mt-5 text-center text-[10px] tracking-wide text-[#a7b09a]">An example of what you can make with Gummfit.</p>
    </div>
  )
}

export default function Hero() {
  return (
    <section className={`relative grid items-center gap-12 pb-16 pt-10 sm:pb-24 sm:pt-16 lg:grid-cols-[0.95fr_1.05fr] lg:gap-14 lg:pb-24 lg:pt-20 ${WRAP}`}>
      <div className="max-w-xl">
        <p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-[#d4ff72] sm:text-xs"><span className="h-1.5 w-1.5 rounded-full bg-[#d4ff72]" /> For the business you’re building</p>
        <h1 className="mt-6 text-[2.9rem] font-medium leading-[1.02] tracking-[-0.065em] text-[#fbfaf4] sm:text-[3.9rem] lg:text-[4.3rem] xl:text-[4.8rem]">
          Small business.<br />Big ideas.<br /><span className="font-serif italic text-[#d4ff72]">Your place online.</span>
        </h1>
        <p className="mt-6 max-w-[26rem] text-base leading-7 text-[#b9c0af] sm:text-lg sm:leading-8">A beautiful website, a shop, and a way to get booked. Bring it all together with tools built by one team.</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link to={SIGNUP_PATH} className={LIME_BUTTON}>Build your website <ArrowRight className="h-4 w-4" /></Link>
          <a href="#features" className="inline-flex items-center justify-center gap-2 px-5 py-3.5 text-sm font-medium text-[#e1e2d9] underline decoration-white/25 underline-offset-4 transition hover:decoration-[#d4ff72] hover:text-[#d4ff72]">Explore what’s included <ArrowDownRight className="h-3.5 w-3.5" /></a>
        </div>
        <p className="mt-5 text-xs text-[#929c86]">AI to get you started. Your creativity to make it yours.</p>
        <div className="mt-9 flex flex-wrap gap-x-5 gap-y-2 border-t border-white/10 pt-5 text-[11px] text-[#b9c0af]">
          {['Made for small business', 'No plugins to manage', 'Your own look & feel'].map((item) => <span key={item} className="flex items-center gap-1.5"><Check className="h-3 w-3 text-[#d4ff72]" />{item}</span>)}
        </div>
      </div>
      <BrowserMockup />
    </section>
  )
}
