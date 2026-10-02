import { Link } from 'react-router-dom'
import { ArrowRight, CalendarDays, Check, Lock, ShoppingBag, Star } from 'lucide-react'
import { LIME_BUTTON, SIGNUP_PATH, WRAP } from './shared'

const products = [
  { name: 'House blend, 12oz', price: '$18', tone: 'bg-[#e8d5bd]' },
  { name: 'Ceramic pour-over', price: '$42', tone: 'bg-[#c7b9dc]' },
  { name: 'Gift card', price: '$25', tone: 'bg-[#dceba8]' },
  { name: 'Tasting class', price: '$35', tone: 'bg-[#f0c9a8]' },
]

/** A mock storefront in a browser frame: the "site + shop" pitch, shown rather
 *  than told. Purely decorative, so it's hidden from assistive tech. */
function BrowserMockup() {
  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-xl select-none">
      <div className="pointer-events-none absolute -inset-10 rounded-full bg-[#d4ff72]/15 blur-3xl" />
      <div className="relative rounded-[1.4rem] border border-white/15 bg-[#f3f0e6] shadow-[0_35px_100px_rgba(0,0,0,0.4)] motion-safe:transition motion-safe:duration-500 lg:rotate-[1.5deg] lg:hover:rotate-0">
        <div className="flex items-center gap-2 border-b border-[#d6d1c4] px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-[#e8796b]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#e9c15a]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#8fc965]" />
          <span className="ml-3 flex min-w-0 flex-1 items-center gap-1.5 rounded-full bg-[#e4dfd2] px-3 py-1 text-[10px] font-medium text-[#6d7066]">
            <Lock className="h-3 w-3 shrink-0" />
            <span className="truncate">ridgelinecoffee.com/shop</span>
          </span>
        </div>
        <div className="p-4 text-[#20251f] sm:p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-black tracking-[-0.04em]">Ridgeline Coffee</span>
            <span className="flex items-center gap-3 text-[10px] font-semibold text-[#6d7066]">
              <span className="hidden sm:inline">Shop</span>
              <span className="hidden sm:inline">Classes</span>
              <span className="flex items-center gap-1 rounded-full bg-[#293229] px-2.5 py-1 text-[#e6f4b3]">
                <ShoppingBag className="h-3 w-3" /> 2
              </span>
            </span>
          </div>
          <div className="mt-4 rounded-2xl bg-[#293229] px-4 py-5 text-[#f6f4eb] sm:px-5">
            <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-[#d4ff72]">Roasted this week</p>
            <p className="mt-2 text-xl font-semibold leading-[1.02] tracking-[-0.05em] sm:text-2xl">Small batch, shipped<br />or picked up.</p>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2.5">
            {products.map((product) => (
              <div key={product.name} className="rounded-xl bg-[#f9f7f1] p-2 shadow-sm">
                <div className={`h-14 rounded-lg sm:h-16 ${product.tone}`} />
                <div className="mt-2 flex items-center justify-between gap-2 px-0.5">
                  <span className="truncate text-[10px] font-semibold">{product.name}</span>
                  <span className="text-[10px] font-bold text-[#596d24]">{product.price}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-1 text-[10px] text-[#6d7066]">
            {[0, 1, 2, 3, 4].map((i) => <Star key={i} className="h-3 w-3 fill-[#a9ca48] text-[#a9ca48]" />)}
            <span className="ml-1">4.9 · 212 reviews</span>
          </div>
        </div>
      </div>

      <div className="absolute -bottom-12 -left-2 rounded-2xl border border-white/10 bg-[#2a342a] px-4 py-3 text-[#f6f4eb] shadow-xl sm:-left-8">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#d4ff72] text-[#263219]"><ShoppingBag className="h-4 w-4" /></span>
          <div><p className="text-xs font-semibold">New order</p><p className="mt-0.5 text-[10px] text-[#b3bbac]">2 items · $60.00 · paid</p></div>
        </div>
      </div>
      <div className="absolute -right-2 -top-5 hidden rounded-2xl border border-white/10 bg-[#2a342a] px-4 py-3 text-[#f6f4eb] shadow-xl sm:block sm:-right-6">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#c7b9dc] text-[#251e2b]"><CalendarDays className="h-4 w-4" /></span>
          <div><p className="text-xs font-semibold">Class booked</p><p className="mt-0.5 text-[10px] text-[#b3bbac]">Sat 10:00 · 4 seats</p></div>
        </div>
      </div>
    </div>
  )
}

export default function Hero() {
  return (
    <section className={`relative z-10 grid items-center gap-16 pb-28 pt-12 sm:pb-36 sm:pt-20 lg:grid-cols-[1fr_1fr] lg:gap-14 ${WRAP}`}>
      <div className="max-w-2xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-[#d4ff72]/25 bg-[#d4ff72]/10 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[#dcff91]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#d4ff72]" /> Websites + online shops for small business
        </div>
        <h1 className="mt-7 text-[2.9rem] font-semibold leading-[0.95] tracking-[-0.07em] text-[#fbfaf4] sm:text-6xl lg:text-7xl">
          Your website and your shop. <span className="text-[#d4ff72]">One price.</span> No plugins.
        </h1>
        <p className="mt-7 max-w-xl text-lg leading-8 text-[#b9bcb0] sm:text-xl">
          Gummfit builds every piece in-house — the site, the store, checkout, bookings, email and your domain. No third-party apps to bolt on, so there's no stack of add-on fees to pay.
        </p>
        <div className="mt-9 flex flex-col gap-3 sm:flex-row">
          <Link to={SIGNUP_PATH} className={LIME_BUTTON}>Build your site <ArrowRight className="h-4 w-4" /></Link>
          <a href="#pricing" className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 px-6 py-3.5 text-sm font-semibold text-[#e1e2d9] transition hover:border-[#d4ff72]/50 hover:text-[#d4ff72]">See pricing</a>
        </div>
        <ul className="mt-10 grid max-w-md grid-cols-2 gap-x-5 gap-y-3 text-xs font-medium text-[#a7ac9d]">
          {['Your own domain', 'Online store', 'Payments built in', 'AI site builder'].map((item) => (
            <li key={item} className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-[#d4ff72]" /> {item}</li>
          ))}
        </ul>
      </div>
      <BrowserMockup />
    </section>
  )
}
