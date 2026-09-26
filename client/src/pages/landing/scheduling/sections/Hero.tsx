import { Link } from 'react-router-dom'
import Stage from '../Stage'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { BOARD, PAPER, hexA } from '../../../../components/marketing/kit/theme'
import { DURATION, LAYOUTS, STILL_FRAME } from '../timeline'
import { Accent, PrimaryButton } from './Chrome'

const loadWeek = () => import('../WeekComposition')

const MUTED = hexA(PAPER, 0.58)

export function Hero({ onContact }: { onContact: () => void }) {
  return (
    // The Draft section inverted: flat dark gray, pulled up under the sticky
    // top bar so it runs to the top edge.
    <header className="sched-dark relative -mt-16 pt-16" style={{ color: PAPER, backgroundColor: BOARD.PAPER }}>
      <div className={`${WRAP} relative pb-28 pt-12 sm:pb-36 sm:pt-20`}>
        <div className="flex items-center justify-between gap-6" style={mono('11px', { color: MUTED })}>
          <span className="flex items-center gap-3">
            <span style={{ color: PAPER, fontWeight: 500 }}>Shift scheduling</span>
            <span aria-hidden className="hidden h-px w-8 sm:inline-block" style={{ backgroundColor: hexA(PAPER, 0.3) }} />
            <span className="hidden sm:inline">Cafés, restaurants &amp; shops</span>
          </span>
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

        {/* the sheet sits flush on the page under one hairline, like the Draft grid */}
        <div className="relative mt-20 pt-4 sm:mt-24" style={{ borderTop: `1px solid ${hexA(PAPER, 0.1)}` }}>
          <Stage
            eager
            load={loadWeek}
            sizes={LAYOUTS}
            durationInFrames={DURATION}
            stillFrame={STILL_FRAME}
            label="Animated example: a café's week drafts itself from the sales forecast, flags a 44-hour week and a 7-hour close-to-open turnaround, moves both shifts to crew with room, and is published."
            surface={{ backgroundColor: BOARD.PAPER }}
            // Pull the media out by the composition's own side padding (48/1600 wide,
            // 28/720 narrow) so the sheet's text lines up with the headline above.
            mediaClassName="-mx-[4.22%] sm:-mx-[3.19%]"
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: MUTED })}>Illustrative week · your draft is built from your own store’s data</span>
                <span className="flex flex-wrap gap-x-6 gap-y-2" style={mono('10.5px', { color: MUTED })}>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-2 w-5 rounded-full" style={{ backgroundColor: hexA(PAPER, 0.3) }} />
                    Shift
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-2 w-5 rounded-full" style={{ boxShadow: `inset 0 0 0 1.5px ${BOARD.RED_PEN}` }} />
                    Flagged
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-2 w-5 rounded-full" style={{ backgroundColor: PAPER }} />
                    Moved
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.STAMP }} />
                    Sent
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
