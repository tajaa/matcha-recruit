import { Link } from 'react-router-dom'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { BOARD, PAPER, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, PrimaryButton } from '../sections/Chrome'
import { CASE, CHECKLIST } from './data'

const MUTED = hexA(PAPER, 0.58)
const STEP = 110 // ms between boxes ticking

/** The case, as HR sees it, ticking itself off. The dots fill from the
 *  `.check-dot` rule in LandingStyles once the card scrolls into view. */
function CaseCard() {
  return (
    <Reveal>
      <div
        className="rounded-2xl p-5 sm:p-7"
        style={{ backgroundColor: BOARD.CARD, boxShadow: `inset 0 0 0 1px ${hexA(PAPER, 0.08)}, 0 40px 80px -48px rgba(0,0,0,.7)` }}
      >
        <div className="flex items-baseline justify-between gap-4" style={mono('10px', { color: MUTED })}>
          <span>
            <span style={{ color: PAPER }}>Case {CASE.number}</span> · {CASE.incident}
          </span>
          <span className="inline-flex items-center gap-2" style={{ color: BOARD.STAMP }}>
            <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: BOARD.STAMP }} />
            Closed
          </span>
        </div>
        <p className="mt-4 text-[1.15rem] font-medium tracking-[-0.02em]" style={{ color: PAPER }}>
          {CASE.title} <span style={{ color: MUTED }}>· {CASE.employee}</span>
        </p>
        <ol className="mt-6 space-y-0.5">
          {CHECKLIST.map((c, i) => (
            <li
              key={c.label}
              className="flex items-center gap-3 rounded-xl px-3 py-2.5"
              style={{ backgroundColor: i % 2 ? 'transparent' : hexA(PAPER, 0.035) }}
            >
              <span
                aria-hidden
                className="check-dot inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ ['--dot' as string]: BOARD.STAMP, ['--d' as string]: `${i * STEP + 500}ms` }}
              />
              <span className="text-[0.95rem]" style={{ color: PAPER }}>
                {c.label}
              </span>
              <span className="ml-auto" style={mono('10px', { color: MUTED })}>
                {c.at}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </Reveal>
  )
}

export function IncidentsHero({ onContact }: { onContact: () => void }) {
  return (
    <header className="sched-dark relative -mt-16 pt-16" style={{ color: PAPER, backgroundColor: BOARD.PAPER }}>
      <div className={`${WRAP} relative pb-28 pt-12 sm:pb-36 sm:pt-20`}>
        <div className="flex items-center justify-between gap-6" style={mono('11px', { color: MUTED })}>
          <span className="flex items-center gap-3">
            <span style={{ color: PAPER, fontWeight: 500 }}>Incident reporting</span>
            <span aria-hidden className="hidden h-px w-8 sm:inline-block" style={{ backgroundColor: hexA(PAPER, 0.3) }} />
            <span className="hidden sm:inline">Report to signed copy</span>
          </span>
          <span className="hidden sm:inline">Illustrative case</span>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-end lg:gap-10">
          <h1 className="lg:col-span-7" style={{ ...display, fontSize: 'clamp(2.75rem, 6vw, 5.75rem)', lineHeight: 0.98 }}>
            <span className="cut-fade block" style={{ ['--d' as string]: '80ms' }}>
              An incident goes in.
            </span>
            <span className="cut-fade block" style={{ ['--d' as string]: '260ms' }}>
              <Accent dark>A closed case</Accent> comes out.
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

        <div className="relative mt-20 grid grid-cols-1 gap-10 pt-10 sm:mt-24 lg:grid-cols-12 lg:gap-14" style={{ borderTop: `1px solid ${hexA(PAPER, 0.1)}` }}>
          <div className="lg:col-span-7">
            <CaseCard />
          </div>
          <dl className="space-y-7 lg:col-span-5 lg:pt-2">
            {[
              { k: 'Matcha does', v: 'Reads the incident against your handbook, opens the case, reviews the letter, files the signed copy, and tells the right people.' },
              { k: 'People decide', v: 'Whether to write someone up, what the letter says, and whether to approve it. Nothing is approved or sent without a person.' },
              { k: 'Who sees it', v: 'Only HR sees the case. Managers see their own write-ups, and nothing medical-adjacent.' },
            ].map((x) => (
              <Reveal key={x.k}>
                <dt style={mono('10px', { color: MUTED })}>{x.k}</dt>
                <dd className="mt-2 max-w-[26rem] text-[0.98rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.82) }}>
                  {x.v}
                </dd>
              </Reveal>
            ))}
          </dl>
        </div>
      </div>
    </header>
  )
}
