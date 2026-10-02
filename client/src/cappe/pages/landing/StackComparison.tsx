import { ArrowRight, CalendarDays, Check, Globe, Mail, Puzzle, ShoppingBag } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EYEBROW, SIGNUP_PATH, WRAP, useReveal } from './shared'

const tools = [
  { name: 'Website', icon: Globe },
  { name: 'Shop', icon: ShoppingBag },
  { name: 'Bookings', icon: CalendarDays },
  { name: 'Newsletter', icon: Mail },
]

export default function StackComparison() {
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()
  return (
    <section className="bg-[#ece6d8] py-20 text-[#293229] sm:py-28">
      <div className={`grid items-center gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20 ${WRAP}`}>
        <div>
          <p className={`${EYEBROW} text-[#637343]`}>Less to piece together</p>
          <h2 className="mt-5 text-4xl font-medium leading-[1.04] tracking-[-0.055em] sm:text-5xl">Run your business.<br /><span className="font-serif italic">Skip the juggling.</span></h2>
          <p className="mt-6 max-w-md text-base leading-7 text-[#626858]">Your website shouldn’t become another job. Our site builder, shop, bookings and newsletters are built together, so there are fewer tools to connect and plugins to keep up with.</p>
          <Link to={SIGNUP_PATH} className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-[#354829] underline decoration-[#354829]/30 underline-offset-4 hover:decoration-[#354829]">Bring it all together <ArrowRight className="h-4 w-4" /></Link>
        </div>
        <div ref={attachReveal} className={`overflow-hidden rounded-2xl border border-[#293229]/15 bg-[#f4efe5] ${revealClass}`}>
          <div className="p-6 sm:p-8">
            <div className="flex items-center gap-2 text-xs font-medium text-[#737866]"><Puzzle className="h-4 w-4" />When your tools live apart</div>
            <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">{tools.map(({ name, icon: Icon }, i) => <div key={name} className={`flex flex-col items-center gap-3 rounded-lg border border-[#293229]/10 bg-[#fcf9f2] px-2 py-5 ${i % 2 ? 'rotate-[3deg]' : '-rotate-[3deg]'}`}><Icon className="h-5 w-5 text-[#7f826f]" strokeWidth={1.4} /><span className="text-[11px] text-[#626858]">{name}</span></div>)}</div>
            <p className="mt-5 text-center text-xs text-[#737866]">Separate logins. More setup. More moving parts.</p>
          </div>
          <div className="bg-[#293a2a] p-6 text-[#f3f1e7] sm:p-8">
            <div className="flex items-center justify-between"><span className="text-base font-semibold tracking-tight">Gummfit</span><span className="flex items-center gap-1.5 text-[10px] text-[#d4ff72]"><Check className="h-3 w-3" />Built together</span></div>
            <div className="mt-5 grid grid-cols-2 gap-2 rounded-xl border border-[#d4ff72]/20 bg-[#d4ff72]/5 p-3 sm:grid-cols-4">{tools.map(({ name, icon: Icon }) => <div key={name} className="flex flex-col items-center gap-2 px-1 py-3"><Icon className="h-5 w-5 text-[#d4ff72]" strokeWidth={1.4} /><span className="text-[11px] text-[#e4e9d8]">{name}</span></div>)}</div>
            <p className="mt-5 text-center text-xs text-[#c0cab3]">One place to build, sell, and stay in touch.</p>
          </div>
        </div>
      </div>
    </section>
  )
}
