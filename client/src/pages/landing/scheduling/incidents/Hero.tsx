import { Link } from 'react-router-dom'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { BOARD, PAPER, hexA } from '../../../../components/marketing/kit/theme'
import Stage from '../Stage'
import { Accent, PrimaryButton } from '../sections/Chrome'
import { CASE_DURATION, CASE_SIZES, CASE_STILL } from './timeline'

const loadCase = () => import('./CaseComposition')

const MUTED = hexA(PAPER, 0.58)

const SPLIT = [
  { k: 'Matcha does', v: 'Reads each incident against your handbook, opens the case, reviews the letter, files the signed copy, and tells the right people.' },
  { k: 'People decide', v: 'Whether to write someone up, what the letter says, and whether it’s approved. Nothing is approved or sent without a person.' },
  { k: 'Who sees it', v: 'Only HR sees the case. Managers see their own write-ups, and nothing medical-adjacent.' },
]

export function IncidentsHero({ onContact }: { onContact: () => void }) {
  return (
    <header className="sched-dark relative -mt-16 pt-16" style={{ color: PAPER, backgroundColor: BOARD.PAPER }}>
      <div className={`${WRAP} relative pb-24 pt-12 sm:pb-32 sm:pt-20`}>
        <div className="flex items-center justify-between gap-6" style={mono('11px', { color: MUTED })}>
          <span className="flex items-center gap-3">
            <span style={{ color: PAPER, fontWeight: 500 }}>Incident reporting</span>
            <span aria-hidden className="hidden h-px w-8 sm:inline-block" style={{ backgroundColor: hexA(PAPER, 0.3) }} />
            <span className="hidden sm:inline">Report to signed copy</span>
          </span>
          <span className="hidden sm:inline">Case HRC-2026-0001</span>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-end lg:gap-10">
          <h1 className="lg:col-span-7" style={{ ...display, fontSize: 'clamp(2.6rem, 6vw, 5.75rem)', lineHeight: 0.98 }}>
            <span className="cut-fade block" style={{ ['--d' as string]: '80ms' }}>
              An incident <span className="whitespace-nowrap">goes in.</span>
            </span>
            <span className="cut-fade block" style={{ ['--d' as string]: '260ms' }}>
              <Accent dark>A closed case</Accent> <span className="whitespace-nowrap">comes out.</span>
            </span>
          </h1>

          <div className="cut-fade lg:col-span-5 lg:pb-3" style={{ ['--d' as string]: '520ms' }}>
            <p className="max-w-[28rem] text-[1.05rem] leading-[1.65]" style={{ color: hexA(PAPER, 0.78) }}>
              Matcha checks every incident against your handbook the moment it’s filed, opens a case when a policy was broken, and carries the
              write-up through review, approval, and a signed copy.{' '}
              <span style={{ color: MUTED }}>It does the paperwork. People make every call.</span>
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

        <div className="relative mt-16 pt-4 sm:mt-24" style={{ borderTop: `1px solid ${hexA(PAPER, 0.1)}` }}>
          <Stage
            eager
            load={loadCase}
            sizes={CASE_SIZES}
            durationInFrames={CASE_DURATION}
            stillFrame={CASE_STILL}
            label="Animated example: a shift lead files an incident, the handbook check marks the attendance clause it breaks at 98% confidence, and the case moves across the HR cases board from New through HR review, delivery and the signed copy to Done."
            surface={{ backgroundColor: BOARD.PAPER }}
            // Pull the media out by the composition's own side padding (48/1600 wide,
            // 39.2/720 narrow) so the board's text lines up with the headline above.
            mediaClassName="-mx-[6.11%] sm:-mx-[3.19%]"
            caption={
              <div className="flex flex-col gap-3 pt-1.5 sm:flex-row sm:items-center sm:justify-between">
                <span style={mono('10.5px', { color: MUTED })}>Illustrative case · checked against your own handbook</span>
                <span className="flex flex-wrap gap-x-6 gap-y-2" style={mono('10.5px', { color: MUTED })}>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.RED_PEN }} />
                    Policy broken
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.AMBER }} />
                    Waiting on a person
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.STAMP }} />
                    Closed
                  </span>
                </span>
              </div>
            }
          />
        </div>

        <dl className="mt-16 grid grid-cols-1 gap-8 sm:mt-20 md:grid-cols-3 md:gap-10" style={{ borderTop: `1px solid ${hexA(PAPER, 0.1)}` }}>
          {SPLIT.map((x, i) => (
            <Reveal key={x.k} delay={i * 90} className="pt-6">
              <dt style={mono('10px', { color: MUTED })}>{x.k}</dt>
              <dd className="mt-3 max-w-[26rem] text-[0.98rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.82) }}>
                {x.v}
              </dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </header>
  )
}
