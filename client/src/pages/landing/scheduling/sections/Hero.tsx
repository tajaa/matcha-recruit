import { Link } from 'react-router-dom'
import Stage from '../Stage'
import { WRAP, display, mono } from '../styles'
import { BOARD, BOARD_GRID, HILITE, PAPER, hexA } from '../theme'
import { DURATION, LAYOUTS, STILL_FRAME } from '../timeline'
import { Accent, PrimaryButton } from './Chrome'

const loadWeek = () => import('../WeekComposition')

const MUTED = hexA(PAPER, 0.58)

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
          <h1 className="lg:col-span-7" style={{ ...display, fontSize: 'clamp(2.75rem, 6vw, 5.75rem)', lineHeight: 0.98 }}>
            <span className="cut-fade block" style={{ ['--d' as string]: '80ms' }}>
              Next week’s schedule,
            </span>
            <span className="cut-fade block" style={{ ['--d' as string]: '260ms' }}>
              <Accent dark>already written.</Accent>
            </span>
          </h1>

          <div className="cut-fade lg:col-span-5 lg:pb-3" style={{ ['--d' as string]: '520ms' }}>
            <p className="max-w-[28rem] text-[1.05rem] leading-[1.65]" style={{ color: hexA(PAPER, 0.78) }}>
              Matcha drafts the week from your sales history, the weather, and who can actually work — then checks every shift for overtime,
              short turnarounds, and availability before you see it.{' '}
              <span style={{ color: MUTED }}>You review. You publish.</span>
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-6">
              <PrimaryButton onClick={onContact} tone="paper">
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
            surface={{ backgroundColor: BOARD.PAPER, ...BOARD_GRID }}
            mediaClassName="overflow-hidden rounded-[10px]"
            mediaStyle={{
              border: `1px solid ${hexA(PAPER, 0.12)}`,
              boxShadow: '0 50px 90px -40px rgba(0,0,0,0.8), 0 18px 30px -20px rgba(0,0,0,0.6)',
            }}
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: MUTED })}>Illustrative week · your draft is built from your own store’s data</span>
                <span className="flex flex-wrap gap-x-5 gap-y-2" style={mono('10.5px', { color: PAPER })}>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-6 rounded-sm" style={{ backgroundColor: HILITE }} />
                    Shift
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-full border-2" style={{ borderColor: BOARD.RED_PEN }} />
                    Flagged
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: BOARD.STAMP }} />
                    Fixed · sent
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
