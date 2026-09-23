import { useRef, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useInView } from '../hooks'
import Stage from '../Stage'
import { WRAP, display, mono } from '../styles'
import { HILITE, INK, INK_SOFT, RED_PEN, STAMP, TAPE, graphPaper, hexA } from '../theme'
import { DURATION, LAYOUTS, STILL_FRAME } from '../timeline'
import { PrimaryButton } from './Chrome'
import { Slip, type SlipTone } from './Cutout'

const loadWeek = () => import('../WeekComposition')

const HEADLINE: { text: string; seed: number; tone: SlipTone; delay: number }[][] = [
  [
    { text: 'Next', seed: 11, tone: 'paper', delay: 80 },
    { text: 'week’s', seed: 12, tone: 'paper', delay: 200 },
  ],
  [{ text: 'schedule,', seed: 13, tone: 'paper', delay: 330 }],
  [
    { text: 'already', seed: 14, tone: 'hilite', delay: 520 },
    { text: 'written.', seed: 15, tone: 'hilite', delay: 660 },
  ],
]

// Torn ends, like a strip pulled off the roll by hand.
const TORN = 'polygon(3% 0, 97% 5%, 100% 28%, 96% 52%, 100% 76%, 97% 100%, 2% 95%, 0 72%, 4% 48%, 0 22%)'

function Tape({ style }: { style: CSSProperties }) {
  return (
    <span
      aria-hidden
      className="absolute z-10 h-[30px] w-[118px] sm:h-[34px] sm:w-[150px]"
      style={{
        backgroundColor: hexA(TAPE, 0.86),
        clipPath: TORN,
        boxShadow: `inset 0 0 0 100px ${hexA('#FFFFFF', 0.08)}`,
        backgroundImage: `repeating-linear-gradient(90deg, ${hexA('#FFFFFF', 0.12)} 0 2px, transparent 2px 7px)`,
        ...style,
      }}
    />
  )
}

/** Red-pen margin note pointing down at the sheet. */
function PenNote() {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useInView(ref, '0px', 0.2)
  return (
    <div ref={ref} aria-hidden className={`pointer-events-none absolute -top-[86px] left-[56%] hidden items-start md:flex ${seen ? 'is-in' : ''}`}>
      <div className="whitespace-nowrap" style={mono('11px', { color: RED_PEN, fontWeight: 700, transform: 'rotate(-3deg)', lineHeight: 1.5 })}>
        Sun 2:00 PM —
        <br />
        watch it write itself
      </div>
      <svg viewBox="0 0 120 80" className="ml-2 mt-2 h-[80px] w-[96px] shrink-0 overflow-visible">
        <path
          className="pen-draw"
          d="M 6 6 C 58 4, 96 22, 92 70"
          fill="none"
          stroke={RED_PEN}
          strokeWidth={2.4}
          strokeLinecap="round"
          pathLength={1}
          style={{ ['--d' as string]: '900ms' }}
        />
        <path
          className="pen-draw"
          d="M 80 58 L 92 72 L 102 56"
          fill="none"
          stroke={RED_PEN}
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          style={{ ['--d' as string]: '1700ms' }}
        />
      </svg>
    </div>
  )
}

export function Hero({ onContact }: { onContact: () => void }) {
  return (
    <header className="relative">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          ...graphPaper(24, 0.5),
          maskImage: 'linear-gradient(to bottom, black 40%, transparent 92%)',
          WebkitMaskImage: 'linear-gradient(to bottom, black 40%, transparent 92%)',
        }}
      />
      <div className={`${WRAP} relative pb-20 pt-10 sm:pt-16`}>
        <div className="flex items-baseline justify-between gap-6" style={mono('11px', { color: INK_SOFT })}>
          <span>Shift scheduling · cafés, restaurants &amp; shops</span>
          <span className="hidden sm:inline">Week 41 · Oct 5–11</span>
        </div>

        {/* Each word is a torn slip pasted onto the sheet, one after another. */}
        <h1 className="mt-6" style={{ ...display, fontSize: 'clamp(3.4rem, 10.6vw, 10.2rem)', lineHeight: 0.9 }}>
          {HEADLINE.map((line, li) => (
            <span key={li} className="flex flex-wrap gap-x-[0.1em]" style={{ marginTop: li ? '0.04em' : 0 }}>
              {line.map((w) => (
                <Slip key={w.text} seed={w.seed} tone={w.tone} delay={w.delay}>
                  {w.text}
                </Slip>
              ))}
            </span>
          ))}
        </h1>

        <div className="cut-fade mt-12 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-end" style={{ ['--d' as string]: '1050ms' }}>
          <p className="max-w-[36rem] text-[1.125rem] leading-[1.6] sm:text-[1.3rem] lg:col-span-7" style={{ color: INK }}>
            Matcha drafts the week from your sales history, the weather, and who can actually work — then checks every shift for overtime,
            short turnarounds, and availability before you see it.{' '}
            <span style={{ color: INK_SOFT }}>You review. You publish.</span>
          </p>
          <div className="flex flex-wrap items-center gap-6 lg:col-span-5 lg:justify-end">
            <PrimaryButton onClick={onContact} torn={31}>
              Book a walkthrough
            </PrimaryButton>
            <Link to="/login" className="sched-link sched-focus rounded text-[15px] font-medium">
              Log in
            </Link>
          </div>
        </div>

        <div className="relative mt-16 sm:mt-28">
          <PenNote />
          <Stage
            eager
            load={loadWeek}
            sizes={LAYOUTS}
            durationInFrames={DURATION}
            stillFrame={STILL_FRAME}
            label="Animated example: a café's week drafts itself from the sales forecast, flags a 44-hour week and a 7-hour close-to-open turnaround, moves both shifts to crew with room, and is published."
            mediaClassName="rounded-[3px]"
            mediaStyle={{
              border: `1.5px solid ${INK}`,
              boxShadow: `0 1px 0 ${hexA(INK, 0.08)}, 0 40px 80px -40px ${hexA(INK, 0.45)}, 0 18px 30px -24px ${hexA(INK, 0.3)}`,
            }}
            decor={
              <>
                <Tape style={{ top: -16, left: '6%', transform: 'rotate(-4deg)' }} />
                <Tape style={{ top: -14, right: '7%', transform: 'rotate(5deg)' }} />
              </>
            }
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: INK_SOFT })}>Illustrative week · your draft is built from your own store’s data</span>
                <span className="flex flex-wrap gap-x-5 gap-y-2" style={mono('10.5px', { color: INK })}>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-6 rounded-sm" style={{ backgroundColor: HILITE }} />
                    Shift
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-full border-2" style={{ borderColor: RED_PEN }} />
                    Flagged
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: STAMP }} />
                    Fixed · published
                  </span>
                </span>
              </div>
            }
          />
        </div>
      </div>
    </header>
  )
}
