import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { CARD, INK, INK_SOFT, PAPER, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { CREW, initials } from '../weekData'
import { Accent, PrimaryButton } from './Chrome'

/** The hero's sent card, at rest: the same 4:12 PM send the animation ends on. */
function SentCard() {
  return (
    <div
      aria-hidden
      className="sent-in w-full max-w-[340px] rounded-xl px-4 py-3.5"
      style={{ backgroundColor: CARD, boxShadow: `0 0 0 1px ${hexA(INK, 0.08)}, 0 1px 2px ${hexA(INK, 0.06)}, 0 18px 40px -18px ${hexA(INK, 0.3)}` }}
    >
      <div className="flex items-center gap-2.5">
        <svg width={18} height={18} viewBox="0 0 18 18" className="shrink-0">
          <circle cx={9} cy={9} r={9} fill={STAMP} />
          <path d="M5 9.4 L7.8 12 L13 6.4" fill="none" stroke={PAPER} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-[15px] font-semibold" style={{ color: INK }}>
          Sent to crew
        </span>
        <span className="ml-auto" style={mono('10.5px', { color: INK_SOFT })}>
          Sun · 4:12 PM
        </span>
      </div>
      <div className="mt-3 flex items-center">
        {CREW.map((c, i) => (
          <span
            key={c.name}
            className="sent-dot inline-flex h-6 w-6 items-center justify-center rounded-full text-[9.5px] font-semibold"
            style={{ marginLeft: i ? -5 : 0, boxShadow: `0 0 0 2px ${CARD}`, ['--d' as string]: `${700 + i * 90}ms` }}
          >
            {initials(c.name)}
          </span>
        ))}
        <span className="ml-auto" style={mono('10.5px', { color: STAMP, fontWeight: 700 })}>
          {CREW.length} notified
        </span>
      </div>
    </div>
  )
}

export function Closing({ onContact }: { onContact: () => void }) {
  return (
    <section className="relative overflow-hidden">
      <div className={`${WRAP} relative py-32 sm:py-48`}>
        <Reveal className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-end">
          <h2 className="lg:col-span-8" style={{ ...display, fontSize: 'clamp(3.2rem, 9vw, 8.5rem)', lineHeight: 0.95 }}>
            Take Sunday night <Accent>back.</Accent>
          </h2>
          <div className="lg:col-span-4 lg:flex lg:justify-end lg:pb-4">
            <SentCard />
          </div>
        </Reveal>
        <Reveal delay={200} className="mt-14 flex flex-wrap items-center gap-x-8 gap-y-5">
          <PrimaryButton onClick={onContact}>Book a walkthrough</PrimaryButton>
          <p className="max-w-sm text-[0.98rem] leading-[1.55]" style={{ color: INK_SOFT }}>
            Twenty minutes with your own store’s week. We’ll draft it live.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
