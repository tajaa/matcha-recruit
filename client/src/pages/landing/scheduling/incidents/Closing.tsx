import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { INK, INK_SOFT, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, PrimaryButton } from '../sections/Chrome'
import { CASE } from './data'

export function IncidentsClosing({ onContact }: { onContact: () => void }) {
  return (
    <section className="relative overflow-hidden">
      <div className={`${WRAP} relative py-32 sm:py-48`}>
        <Reveal className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-end">
          <h2 className="lg:col-span-8" style={{ ...display, fontSize: 'clamp(3.2rem, 9vw, 8.5rem)', lineHeight: 0.95 }}>
            Every incident, <Accent>closed.</Accent>
          </h2>
          <div
            aria-hidden
            className="sent-in w-full max-w-[340px] rounded-xl px-4 py-3.5 lg:ml-auto"
            style={{ backgroundColor: '#FBFCF9', boxShadow: `0 0 0 1px ${hexA(INK, 0.08)}, 0 1px 2px ${hexA(INK, 0.06)}, 0 18px 40px -18px ${hexA(INK, 0.3)}` }}
          >
            <div className="flex items-center gap-2.5">
              <svg width={18} height={18} viewBox="0 0 18 18" className="shrink-0">
                <circle cx={9} cy={9} r={9} fill={STAMP} />
                <path d="M5 9.4 L7.8 12 L13 6.4" fill="none" stroke="#F2F4EF" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-[15px] font-semibold" style={{ color: INK }}>
                Case closed
              </span>
              <span className="ml-auto" style={mono('10.5px', { color: INK_SOFT })}>
                Wed · 2:30 PM
              </span>
            </div>
            <p className="mt-3" style={mono('10.5px', { color: INK_SOFT })}>
              {CASE.number} · signed copy filed
            </p>
          </div>
        </Reveal>
        <Reveal delay={200} className="mt-14 flex flex-wrap items-center gap-x-8 gap-y-5">
          <PrimaryButton onClick={onContact}>Book a walkthrough</PrimaryButton>
          <p className="max-w-sm text-[0.98rem] leading-[1.55]" style={{ color: INK_SOFT }}>
            Twenty minutes with your own handbook. We’ll file a test incident live.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
