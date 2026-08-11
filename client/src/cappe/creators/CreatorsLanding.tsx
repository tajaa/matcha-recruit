import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Check,
  CircleDollarSign,
  Handshake,
  HeartHandshake,
  Play,
  Sparkles,
  Stars,
} from 'lucide-react'

const creatorBenefits = [
  {
    icon: Sparkles,
    number: '01',
    title: 'A media kit that feels like you',
    body: 'Make your work, audience and rates impossible to overlook — in one polished, shareable profile.',
  },
  {
    icon: BadgeCheck,
    number: '02',
    title: 'Your reach, substantiated',
    body: 'Verified audience signals give great brands the confidence to say yes to your actual value.',
  },
  {
    icon: CircleDollarSign,
    number: '03',
    title: 'Clear terms. On-time pay.',
    body: 'Send offers, negotiate, review approvals and get paid without a maze of DMs and invoices.',
  },
]

const protections = [
  'Usage rights are always explicit and time-bound.',
  'Whitelisting is paid usage — never a free afterthought.',
  'Approved work auto-approves if a brand goes silent.',
  'A cancelled campaign still pays for earned work.',
]

// Public marketing page at /gummfit/creators. It intentionally has its own
// warmer, editorial visual language — Gummfit Creators is a distinct product.
export default function CreatorsLanding() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#10110f] text-[#f7f5ee] selection:bg-[#d4ff72] selection:text-[#11140d]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[43rem] bg-[radial-gradient(circle_at_82%_9%,rgba(228,255,154,0.18),transparent_24rem),radial-gradient(circle_at_17%_28%,rgba(192,145,255,0.14),transparent_23rem)]" />

      <header className="relative z-10 px-5 py-5 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <Link to="/gummfit/creators" className="group flex items-center gap-2.5" aria-label="Gummfit Creators home">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72] text-sm font-black tracking-tighter text-[#14170f] shadow-[0_0_28px_rgba(212,255,114,0.25)]">G</span>
            <span className="text-sm font-semibold tracking-[-0.02em] text-[#f7f5ee]">Gummfit <em className="font-normal text-[#d4ff72]">Creators</em></span>
          </Link>
          <nav className="flex items-center gap-3 sm:gap-5">
            <Link to="/gummfit/creators/directory" className="hidden text-sm font-medium text-[#c9c9c0] transition hover:text-white sm:block">Explore talent</Link>
            <Link to="/gummfit/creators/login" className="text-sm font-medium text-[#deded5] transition hover:text-white">Sign in</Link>
            <Link to="/gummfit/creators/signup" className="rounded-full bg-[#d4ff72] px-4 py-2 text-sm font-semibold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a] sm:px-5">Join creators</Link>
          </nav>
        </div>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl items-center gap-12 px-5 pb-20 pt-14 sm:px-8 md:pb-28 md:pt-20 lg:grid-cols-[1.02fr_0.98fr] lg:gap-16 lg:px-12">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#d4ff72]/25 bg-[#d4ff72]/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#dcff91]">
            <Stars className="h-3.5 w-3.5" /> A better way to partner
          </div>
          <h1 className="mt-7 max-w-xl text-[3.25rem] font-semibold leading-[0.94] tracking-[-0.065em] text-[#fbfaf5] sm:text-6xl lg:text-7xl">
            Your work is the <span className="relative whitespace-nowrap text-[#d4ff72]"><span className="relative z-10">main event.</span><span className="absolute inset-x-0 bottom-1 h-3 -rotate-1 bg-[#d4ff72]/15" /></span>
          </h1>
          <p className="mt-7 max-w-lg text-lg leading-8 text-[#bdbeb4] sm:text-xl">
            Gummfit Creators is the place to turn your point of view into partnerships that respect your work, your audience, and your time.
          </p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link to="/gummfit/creators/signup" className="inline-flex items-center justify-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a] hover:shadow-[0_12px_30px_rgba(212,255,114,0.16)]">
              Build your profile <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/gummfit/creators/directory" className="inline-flex items-center justify-center gap-2 px-4 py-3 text-sm font-semibold text-[#e5e5dc] transition hover:text-[#d4ff72]">
              See the network <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="mt-11 flex items-center gap-4 text-sm text-[#a8a99f]">
            <div className="flex -space-x-2">
              {['#e2a8a0', '#b8c88a', '#9eb4de', '#d4ae82'].map((color, i) => <span key={color} className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-[#10110f] text-[9px] font-bold text-[#20241a]" style={{ backgroundColor: color }}>{['M', 'A', 'J', 'K'][i]}</span>)}
            </div>
            <span><strong className="font-semibold text-[#f1f0e9]">Made for creators</strong><br />with a point of view</span>
          </div>
        </div>

        <div className="relative mx-auto w-full max-w-xl lg:mr-0">
          <div className="absolute -inset-8 rounded-full bg-[#d4ff72]/10 blur-3xl" />
          <div className="relative rotate-[-2deg] rounded-[2rem] border border-white/10 bg-[#22251f] p-3 shadow-2xl shadow-black/40 transition duration-500 hover:rotate-0">
            <div className="overflow-hidden rounded-[1.55rem] bg-[#f0eddf] p-4 text-[#1d201a] sm:p-5">
              <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.15em] text-[#737569]">
                <span>Creator profile</span><span>•••</span>
              </div>
              <div className="relative mt-4 h-36 overflow-hidden rounded-2xl bg-[#c1acdb] sm:h-44">
                <div className="absolute -right-7 -top-8 h-36 w-36 rounded-full bg-[#efb994]" />
                <div className="absolute bottom-0 left-0 h-28 w-2/3 rounded-tr-[5rem] bg-[#9db77d]" />
                <div className="absolute bottom-6 left-7 h-11 w-11 rounded-full border-[5px] border-[#efb994] bg-[#2b3122]" />
                <div className="absolute bottom-6 left-14 h-5 w-20 rotate-[-24deg] rounded-full bg-[#2b3122]" />
                <div className="absolute right-5 top-5 rounded-full bg-[#f8f4e9]/80 px-2.5 py-1 text-[9px] font-bold tracking-wide text-[#3f4534]">STYLE • FOOD • LIFE</div>
              </div>
              <div className="relative -mt-8 mx-3 rounded-2xl bg-white p-4 shadow-lg shadow-[#4a4c3d]/10 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#2d3623] text-sm font-bold text-[#d4ff72]">A</div>
                    <div><div className="flex items-center gap-1 text-sm font-bold">Avery Lane <BadgeCheck className="h-3.5 w-3.5 fill-[#a8dd4d] text-[#4a611c]" /></div><p className="mt-0.5 text-[11px] text-[#75776d]">@averymakesit</p></div>
                  </div>
                  <span className="rounded-full bg-[#eff8d8] px-2 py-1 text-[9px] font-bold text-[#52671f]">AVAILABLE</span>
                </div>
                <p className="mt-4 text-sm leading-5 text-[#4d5047]">A tasteful life, a perfectly poured drink, and the little details that make a place memorable.</p>
                <div className="mt-4 grid grid-cols-3 border-y border-[#e8e7df] py-3 text-center">
                  <div><p className="text-sm font-bold">182K</p><p className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#84867c]">Community</p></div>
                  <div className="border-x border-[#e8e7df]"><p className="text-sm font-bold">4.8%</p><p className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#84867c]">Engagement</p></div>
                  <div><p className="text-sm font-bold">14</p><p className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#84867c]">Campaigns</p></div>
                </div>
                <div className="mt-4 flex gap-2">
                  {[['Campaign reel', '#efb994'], ['Day in Lisbon', '#b8c88a'], ['The pour', '#b2c4e7']].map(([label, color]) => <div key={label} className="flex-1"><div className="relative aspect-[4/3] overflow-hidden rounded-lg" style={{ backgroundColor: color }}><Play className="absolute bottom-1.5 left-1.5 h-4 w-4 fill-white text-white" /></div><p className="mt-1 truncate text-[9px] font-medium text-[#5a5c53]">{label}</p></div>)}
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between px-2 pb-1 text-[10px] font-semibold text-[#797b70]"><span>RATE CARD FROM $950</span><span>VIEW MEDIA KIT →</span></div>
            </div>
          </div>
          <div className="absolute -bottom-5 -left-4 rotate-[4deg] rounded-2xl border border-white/10 bg-[#2d3227] px-4 py-3 shadow-xl shadow-black/25 sm:-left-8 sm:px-5">
            <div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#d4ff72] text-[#263019]"><Handshake className="h-4 w-4" /></span><div><p className="text-xs font-semibold text-[#f7f5ee]">Collab offer received</p><p className="text-[10px] text-[#a7aa9b]">Terms ready for your review</p></div></div>
          </div>
        </div>
      </section>

      <section className="relative border-y border-white/10 bg-[#171a15] px-5 py-5 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 text-xs font-semibold uppercase tracking-[0.16em] text-[#8e9284]">
          <span>One profile. Better opportunities.</span>
          <div className="flex gap-5 text-[#d6d7cd] sm:gap-9"><span>MEDIA KIT</span><span>RATE CARD</span><span>DEALS</span><span>PAYOUTS</span></div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#d4ff72]">Made for the way you work</p>
          <h2 className="mt-4 text-4xl font-semibold leading-[0.98] tracking-[-0.055em] text-[#f7f5ee] sm:text-5xl">A network that knows a creator is a business.</h2>
        </div>
        <div className="mt-14 grid gap-px overflow-hidden rounded-[1.5rem] border border-white/10 bg-white/10 md:grid-cols-3">
          {creatorBenefits.map(({ icon: Icon, number, title, body }) => <article key={number} className="group bg-[#181b16] p-7 transition hover:bg-[#21261d] sm:p-8"><div className="flex items-start justify-between"><span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#d4ff72]/10 text-[#d4ff72]"><Icon className="h-5 w-5" /></span><span className="text-xs font-semibold tracking-widest text-[#686d60]">{number}</span></div><h3 className="mt-12 text-xl font-semibold tracking-[-0.035em] text-[#f4f2ea]">{title}</h3><p className="mt-3 max-w-xs text-sm leading-6 text-[#aeb0a4]">{body}</p></article>)}
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#e7e1d1] px-5 py-20 text-[#20241d] sm:px-8 lg:px-12 lg:py-28">
        <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20">
          <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#607622]">Creator-first, by design</p><h2 className="mt-5 text-4xl font-semibold leading-[0.98] tracking-[-0.055em] sm:text-5xl">Good partnerships start with good boundaries.</h2><p className="mt-6 max-w-md text-base leading-7 text-[#54594e]">You bring the creative direction. We make sure the business side keeps up — from a first offer through final payout.</p></div>
          <div className="grid gap-3 sm:grid-cols-2">{protections.map((protection, index) => <div key={protection} className={`rounded-2xl p-6 ${index === 0 ? 'bg-[#c9e477]' : index === 3 ? 'bg-[#baabd2] text-[#27222f]' : 'bg-[#f4f0e5]'}`}><span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#20241d]/10"><Check className="h-4 w-4" /></span><p className="mt-10 text-lg font-semibold leading-6 tracking-[-0.025em]">{protection}</p></div>)}</div>
        </div>
      </section>

      <section className="relative px-5 py-24 text-center sm:px-8 lg:px-12 lg:py-32">
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#d4ff72]/10 blur-3xl" />
        <div className="relative mx-auto max-w-2xl"><HeartHandshake className="mx-auto h-7 w-7 text-[#d4ff72]" /><h2 className="mt-5 text-4xl font-semibold leading-[0.98] tracking-[-0.055em] text-[#f7f5ee] sm:text-5xl">Make work you’re proud to put your name on.</h2><p className="mt-5 text-lg text-[#aeb0a4]">Set up your profile in minutes. The right partnership could start today.</p><Link to="/gummfit/creators/signup" className="mt-9 inline-flex items-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a]">Join Gummfit Creators <ArrowRight className="h-4 w-4" /></Link></div>
      </section>

      <footer className="border-t border-white/10 px-5 py-7 text-xs text-[#85897d] sm:px-8 lg:px-12"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-3 sm:flex-row"><span>© {new Date().getFullYear()} Gummfit Creators</span><div className="flex gap-5"><Link to="/gummfit/creators/directory" className="hover:text-white">Explore talent</Link><Link to="/gummfit/creators/login" className="hover:text-white">Sign in</Link></div></div></footer>
    </main>
  )
}
