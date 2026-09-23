import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import Stage from '../Stage'
import { WRAP, display, mono } from '../styles'
import { HILITE, PAPER, RED_PEN, STAMP, TAPE, hexA } from '../theme'
import { DURATION, LAYOUTS, STILL_FRAME } from '../timeline'
import { PrimaryButton } from './Chrome'
import { Slip, type SlipTone } from './Cutout'

const loadWeek = () => import('../WeekComposition')

const MUTED = hexA(PAPER, 0.58)

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

export function Hero({ onContact }: { onContact: () => void }) {
  return (
    // Pulled up under the sticky top bar so the gradient runs to the top edge.
    <header
      className="sched-dark relative -mt-16 pt-16"
      style={{
        color: PAPER,
        background: 'radial-gradient(120% 80% at 15% 0%, #223127 0%, rgba(34,49,39,0) 60%), linear-gradient(170deg, #161C18 0%, #0E100F 55%, #090A09 100%)',
      }}
    >
      <div className={`${WRAP} relative pb-20 pt-10 sm:pt-14`}>
        <div className="flex items-baseline justify-between gap-6" style={mono('11px', { color: MUTED })}>
          <span>Shift scheduling · cafés, restaurants &amp; shops</span>
          <span className="hidden sm:inline">Week 41 · Oct 5–11</span>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-end lg:gap-10">
          {/* Each word is a torn slip pasted onto the sheet, one after another. */}
          <h1 className="lg:col-span-7" style={{ ...display, fontSize: 'clamp(2.1rem, 4.6vw, 4.4rem)', lineHeight: 0.9 }}>
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

          <div className="cut-fade lg:col-span-5 lg:pb-2" style={{ ['--d' as string]: '900ms' }}>
            <p className="max-w-[30rem] text-[1.05rem] leading-[1.6] sm:text-[1.15rem]" style={{ color: hexA(PAPER, 0.9) }}>
              Matcha drafts the week from your sales history, the weather, and who can actually work — then checks every shift for overtime,
              short turnarounds, and availability before you see it.{' '}
              <span style={{ color: MUTED }}>You review. You publish.</span>
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-6">
              <PrimaryButton onClick={onContact} torn={31} tone="paper">
                Book a walkthrough
              </PrimaryButton>
              <Link to="/login" className="sched-link sched-focus rounded text-[15px] font-medium">
                Log in
              </Link>
            </div>
          </div>
        </div>

        <div className="relative mt-14 sm:mt-16">
          <Stage
            eager
            load={loadWeek}
            sizes={LAYOUTS}
            durationInFrames={DURATION}
            stillFrame={STILL_FRAME}
            label="Animated example: a café's week drafts itself from the sales forecast, flags a 44-hour week and a 7-hour close-to-open turnaround, moves both shifts to crew with room, and is published."
            mediaClassName="rounded-[3px]"
            mediaStyle={{
              border: `1px solid ${hexA(PAPER, 0.25)}`,
              boxShadow: '0 50px 90px -40px rgba(0,0,0,0.8), 0 18px 30px -20px rgba(0,0,0,0.6)',
            }}
            decor={
              <>
                <Tape style={{ top: -16, left: '6%', transform: 'rotate(-4deg)' }} />
                <Tape style={{ top: -14, right: '7%', transform: 'rotate(5deg)' }} />
              </>
            }
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: MUTED })}>Illustrative week · your draft is built from your own store’s data</span>
                <span className="flex flex-wrap gap-x-5 gap-y-2" style={mono('10.5px', { color: PAPER })}>
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
