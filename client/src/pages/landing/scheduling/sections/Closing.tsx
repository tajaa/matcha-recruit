import { Reveal } from '../motion'
import { WRAP, display, mono } from '../styles'
import { INK_SOFT, PAPER, STAMP, graphPaper, hexA } from '../theme'
import { PrimaryButton } from './Chrome'

export function Closing({ onContact }: { onContact: () => void }) {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0" style={graphPaper(24, 0.45)} />
      <div className={`${WRAP} relative py-28 sm:py-44`}>
        <Reveal className="relative">
          <h2 style={{ ...display, fontWeight: 800, fontSize: 'clamp(3.6rem, 12vw, 11.5rem)', lineHeight: 0.82 }}>
            <span className="block">Take Sunday</span>
            <span className="block">
              night <span className="sched-hilite sched-hilite-scroll">back.</span>
            </span>
          </h2>
          {/* the hero's 4:12 PM stamp, landing on the promise */}
          <div
            aria-hidden
            className="stamp-in pointer-events-none absolute bottom-[-18%] right-0 hidden rounded-[10px] px-6 pb-3 pt-2 text-center sm:block lg:bottom-[4%] lg:right-[2%]"
            style={{ border: `6px double ${STAMP}`, color: STAMP, backgroundColor: hexA(PAPER, 0.6), mixBlendMode: 'multiply' }}
          >
            <div style={{ ...display, fontWeight: 800, fontSize: 'clamp(2.6rem, 5vw, 4.6rem)', letterSpacing: '0.04em' }}>Published</div>
            <div className="mt-1" style={mono('11px', { fontWeight: 700, letterSpacing: '0.16em' })}>
              Sun 4:12 PM · 8 crew notified
            </div>
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
