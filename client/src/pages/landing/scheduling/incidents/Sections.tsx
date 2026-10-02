import type { ReactNode } from 'react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, glassChip, glassPane, mono } from '../../../../components/marketing/kit/styles'
import { AMBER, BOARD, INK, INK_SOFT, PAPER, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, Glows, StepHead } from '../sections/Chrome'
import { CASE, FLAG_THRESHOLD, LAYERS, MATCHES, OUTCOME, SIGNED_CHECKS, type Outcome } from './data'

const ROW = 70 // ms between rows ticking in
const DOT: Record<Outcome, string> = { holds: AMBER, noted: INK, fix: STAMP }

/** A frosted pane with a mono header line, like the Check report. */
function Pane({ left, right, children, glows }: { left: ReactNode; right?: ReactNode; children: ReactNode; glows?: [string, string] }) {
  return (
    <div className="relative mt-16">
      {glows && <Glows green={glows[0]} amber={glows[1]} />}
      <div className="relative rounded-[28px] p-2 sm:p-3" style={glassPane}>
        <div className="flex items-baseline justify-between gap-6 px-4 pb-3 pt-3" style={mono('9.5px', { color: INK_SOFT })}>
          <span>{left}</span>
          {right && <span className="hidden sm:inline">{right}</span>}
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ k, v, wide }: { k: string; v: string; wide?: boolean }) {
  return (
    <div className={wide ? 'sm:col-span-2' : ''}>
      <dt style={mono('9.5px', { color: INK_SOFT })}>{k}</dt>
      <dd className="mt-1.5 text-[0.98rem] leading-[1.55]" style={{ color: INK }}>
        {v}
      </dd>
    </div>
  )
}

/** Tue 8:02 AM — the incident, as the shift lead files it. */
export function Report() {
  return (
    <section id="report" className={`${WRAP} py-28 sm:py-44`}>
      <StepHead
        split
        step="report"
        title={
          <>
            A shift lead <Accent>files it.</Accent>
          </>
        }
      >
        Jonah missed three shifts and never called. Ana files the incident from the report form. A crew member can also report from a link, without
        logging in.
      </StepHead>
      <Pane
        left={
          <>
            <span style={{ color: INK }}>Incident report</span> · {CASE.incident}
          </>
        }
        right="Filed Tue 8:02 AM"
        glows={['16% 24%', '84% 80%']}
      >
        <Reveal className="rounded-2xl px-5 py-6 sm:px-7" style={glassChip}>
          <dl className="grid grid-cols-1 gap-x-10 gap-y-6 sm:grid-cols-2">
            <Field k="Title" v="Repeated no-call/no-show" wide />
            <Field k="Reported by" v={`${CASE.reporter} · Shift lead`} />
            <Field k="Involved" v={`${CASE.employee} · Barista`} />
            <Field k="Location" v="Downtown" />
            <Field k="Occurred" v="Tue, Thu and Sat this month" />
            <Field
              k="What happened"
              v="Missed three scheduled shifts without calling or texting the shift lead. The opening shift had to be covered each time."
              wide
            />
          </dl>
        </Reveal>
      </Pane>
    </section>
  )
}

/** Tue 8:02 AM · +10 s — checked against the handbook. */
export function Triage() {
  return (
    <section id="triage" className={`${WRAP} pb-28 sm:pb-44`}>
      <StepHead
        split
        step="triage"
        title={
          <>
            Checked against <Accent>your</Accent> handbook.
          </>
        }
      >
        Within seconds of filing, Matcha reads the incident against your handbook and policies and reports which ones it may break, by name. It only
        reports. Whether a case opens is a fixed rule you can see and change. The reporting manager and HR are told.
      </StepHead>
      <Pane
        left={
          <>
            <span style={{ color: INK }}>Handbook check</span> · {CASE.incident}
          </>
        }
        right={`A case opens at ${FLAG_THRESHOLD}%+ on a violated or bent policy`}
        glows={['20% 18%', '80% 82%']}
      >
        <ol className="space-y-0.5">
          {MATCHES.map((m, i) => (
            <Reveal
              key={m.policy}
              as="li"
              delay={i * ROW}
              className="rounded-2xl px-4 py-4 lg:grid lg:grid-cols-12 lg:items-center lg:gap-x-6"
              style={{ backgroundColor: i % 2 ? 'transparent' : 'rgba(255, 255, 255, 0.4)' }}
            >
              <div className="lg:col-span-5">
                <h3 className="text-[0.98rem] font-medium leading-snug tracking-[-0.015em]" style={{ color: INK }}>
                  {m.policy}
                </h3>
                <p className="mt-0.5" style={mono('9.5px', { color: INK_SOFT })}>
                  {m.relevance} · {m.confidence}%
                </p>
              </div>
              <div className="mt-3 lg:col-span-4 lg:mt-0">
                {/* the bar fills to the confidence; the tick is the opening threshold */}
                <div
                  className="relative h-1.5 rounded-full"
                  style={{ backgroundColor: hexA(INK, 0.08) }}
                  role="img"
                  aria-label={`${m.confidence}% confidence; a case opens at ${FLAG_THRESHOLD}%`}
                >
                  <div
                    className="grow-x h-full rounded-full"
                    style={{ width: `${m.confidence}%`, backgroundColor: m.opens ? STAMP : hexA(INK, 0.35), ['--d' as string]: `${i * ROW + 250}ms` }}
                  />
                  <span aria-hidden className="absolute -top-1 h-3.5 w-px" style={{ left: `${FLAG_THRESHOLD}%`, backgroundColor: hexA(INK, 0.45) }} />
                </div>
              </div>
              <div className="mt-3 lg:col-span-3 lg:mt-0 lg:flex lg:justify-end">
                <span
                  className="inline-flex items-center gap-2 rounded-full px-2.5 py-1"
                  style={{ ...mono('9px', { color: INK }), backgroundColor: hexA(m.opens ? STAMP : INK, m.opens ? 0.12 : 0.06) }}
                >
                  <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: m.opens ? STAMP : hexA(INK, 0.4) }} />
                  {m.opens ? 'Case opened' : 'Noted'}
                </span>
              </div>
            </Reveal>
          ))}
        </ol>
        <Reveal delay={MATCHES.length * ROW} className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {[
            { t: 'A check that can’t run isn’t clean', d: 'It’s recorded as unknown and opens nothing. It’s never read as a pass.' },
            { t: 'The story stays put', d: 'A case keeps policy titles and confidence, not the narrative. Notices carry numbers and titles only.' },
            { t: 'Closed stays closed', d: 'A case HR closed or dismissed is never reopened by a later check.' },
          ].map((x) => (
            <div key={x.t} className="rounded-2xl px-4 py-3.5" style={glassChip}>
              <div style={mono('9.5px', { color: INK })}>{x.t}</div>
              <p className="mt-1.5 text-[0.85rem] leading-snug" style={{ color: INK_SOFT }}>
                {x.d}
              </p>
            </div>
          ))}
        </Reveal>
      </Pane>
    </section>
  )
}

/** Tue 8:40 AM — the letter, reviewed before HR sees it. */
export function WriteUp() {
  const counts = (Object.keys(OUTCOME) as Outcome[]).map((o) => ({ o, n: LAYERS.filter((l) => l.outcome === o).length }))
  return (
    <section id="writeup" className={`${WRAP} pb-28 sm:pb-44`}>
      <StepHead
        split
        step="writeup"
        title={
          <>
            Reviewed <Accent>before</Accent> HR sees it.
          </>
        }
      >
        Ana sends the letter as an upload, a Drive file, or a Google Doc link. It’s filed in HR’s Drive, then reviewed in four layers. The manager sees
        only what they can act on, never the leave findings.
      </StepHead>
      <Pane
        left={
          <>
            <span style={{ color: INK }}>Write-up review</span> · {CASE.number}
          </>
        }
        right="Written warning · attendance"
        glows={['18% 22%', '82% 78%']}
      >
        <ol className="space-y-0.5">
          {LAYERS.map((l, i) => (
            <Reveal
              key={l.name}
              as="li"
              delay={i * ROW}
              className="rounded-2xl px-4 py-3.5 lg:grid lg:grid-cols-12 lg:items-center lg:gap-x-6"
              style={{ backgroundColor: i % 2 ? 'transparent' : 'rgba(255, 255, 255, 0.4)' }}
            >
              <div className="lg:col-span-5">
                <h3 className="text-[0.98rem] font-medium leading-snug tracking-[-0.015em]" style={{ color: INK }}>
                  {l.name}
                </h3>
                <p className="mt-0.5 text-[0.85rem] leading-[1.5]" style={{ color: INK_SOFT }}>
                  {l.detail}
                </p>
              </div>
              <div className="mt-2 lg:col-span-4 lg:mt-0">
                <span style={mono('10px', { color: INK_SOFT })}>{l.example}</span>
              </div>
              <div className="mt-2 lg:col-span-3 lg:mt-0 lg:flex lg:justify-end">
                <span
                  className="inline-flex shrink-0 items-center gap-2 rounded-full px-2.5 py-1"
                  style={{ ...mono('9px', { color: INK }), backgroundColor: hexA(DOT[l.outcome], 0.09) }}
                >
                  <span
                    aria-hidden
                    className="check-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ ['--dot' as string]: DOT[l.outcome], ['--d' as string]: `${i * ROW + 350}ms` }}
                  />
                  {OUTCOME[l.outcome].label}
                </span>
              </div>
            </Reveal>
          ))}
        </ol>
        <Reveal delay={LAYERS.length * ROW} className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {counts.map(({ o, n }) => (
            <div key={o} className="rounded-2xl px-4 py-3.5" style={glassChip}>
              <div className="flex items-center gap-2" style={mono('9.5px', { color: INK })}>
                <span aria-hidden className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: DOT[o] }} />
                {n} {OUTCOME[o].label}
              </div>
              <p className="mt-1.5 text-[0.85rem] leading-snug" style={{ color: INK_SOFT }}>
                {OUTCOME[o].means}
              </p>
            </div>
          ))}
        </Reveal>
      </Pane>
    </section>
  )
}

const RULE = hexA(PAPER, 0.1)

/** Tue 9:15 AM — HR decides. The dark band, like Cost on the other tab. */
export function Approve() {
  return (
    <section id="approve" className="sched-dark" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <div className={`${WRAP} py-28 sm:py-44`}>
        <StepHead split step="approve" dark title="HR decides. Matcha re-checks.">
          HR reads the letter next to the review and either approves it or sends it back with a reason the manager can act on. Leave records can change
          between review and approval, so the protected-leave check runs again at the moment HR approves.
        </StepHead>

        <div className="mt-16 grid grid-cols-1 lg:grid-cols-2" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
          <Reveal className="flex flex-col py-12 lg:border-r lg:pr-14" style={{ borderColor: RULE }}>
            <CellLabel n="01" dark>
              The decision
            </CellLabel>
            <div className="mt-8 flex flex-wrap gap-3">
              <span className="inline-flex h-11 items-center rounded-full px-6 text-[15px] font-medium" style={{ backgroundColor: PAPER, color: BOARD.PAPER }}>
                Approve
              </span>
              <span className="inline-flex h-11 items-center rounded-full px-6 text-[15px] font-medium" style={{ boxShadow: `inset 0 0 0 1px ${hexA(PAPER, 0.35)}` }}>
                Send back
              </span>
            </div>
            <p className="mt-8 max-w-[28rem] text-[0.98rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.7) }}>
              A send-back needs a real reason, twenty characters at least, and the manager sees it. A button pressed twice, or on a stale screen, can’t skip
              a step.
            </p>
          </Reveal>

          <Reveal delay={120} className="flex flex-col border-t py-12 lg:border-t-0 lg:pl-14" style={{ borderColor: RULE }}>
            <CellLabel n="02" dark>
              Then it moves
            </CellLabel>
            <ol className="mt-8">
              {[
                { at: 'Tue 9:15 AM', t: 'Approved to deliver', d: 'Protected-leave check re-run from the same inputs.' },
                { at: 'Tue 9:30 AM', t: 'Delivered', d: 'The manager or HR marks the letter handed over.' },
              ].map((x) => (
                <li key={x.t} className="grid grid-cols-[6.5rem_1fr] gap-4 py-4" style={{ borderTop: `1px solid ${RULE}` }}>
                  <span style={mono('10px', { color: hexA(PAPER, 0.55) })}>{x.at}</span>
                  <span>
                    <span className="block text-[0.98rem]" style={{ color: PAPER }}>
                      {x.t}
                    </span>
                    <span className="mt-1 block text-[0.88rem] leading-[1.55]" style={{ color: hexA(PAPER, 0.6) }}>
                      {x.d}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

/** Wed 2:30 PM — the signed copy, filed and checked. */
export function Signed() {
  return (
    <section id="signed" className={`${WRAP} py-28 sm:py-44`}>
      <StepHead
        split
        step="signed"
        title={
          <>
            Signed, checked, <Accent>filed.</Accent>
          </>
        }
      >
        The manager uploads the signed copy as a PDF or a phone photo. It’s filed straight away in HR’s Drive under the employee’s name, then read to
        make sure it’s the right letter, actually signed. Then the case closes.
      </StepHead>
      <Pane
        left={
          <>
            <span style={{ color: INK }}>Signed copy</span> · {CASE.number}
          </>
        }
        right="Checked Wed 2:30 PM"
        glows={['16% 26%', '84% 76%']}
      >
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          <Reveal className="rounded-2xl px-5 py-6 sm:px-7" style={glassChip}>
            <div style={mono('9.5px', { color: INK_SOFT })}>Filed in Drive</div>
            <p className="mt-3 break-words" style={mono('11px', { color: INK, letterSpacing: '0.04em' })}>
              HR / Discipline / Signed / Brooks, Jonah
            </p>
            <p className="mt-2 break-words" style={mono('11px', { color: INK_SOFT, letterSpacing: '0.04em' })}>
              Brooks_Jonah_written-warning_2026-10-07.pdf
            </p>
            <p className="mt-5 text-[0.88rem] leading-[1.55]" style={{ color: INK_SOFT }}>
              Named from your own filename template, so the file is already in the format you audit against. The HR read is logged.
            </p>
          </Reveal>
          <Reveal delay={120} className="rounded-2xl px-5 py-6 sm:px-7" style={glassChip}>
            <div style={mono('9.5px', { color: INK_SOFT })}>What the check reads</div>
            <ul className="mt-3 space-y-2.5">
              {SIGNED_CHECKS.map((c, i) => (
                <li key={c} className="flex items-center gap-3 text-[0.95rem]" style={{ color: INK }}>
                  <span
                    aria-hidden
                    className="check-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ ['--dot' as string]: STAMP, ['--d' as string]: `${i * ROW + 400}ms` }}
                  />
                  {c}
                </li>
              ))}
            </ul>
            <p className="mt-5 text-[0.88rem] leading-[1.55]" style={{ color: INK_SOFT }}>
              A check that can’t run is never a pass. The case waits for HR. Anything the employee writes on the page goes to HR only.
            </p>
          </Reveal>
        </div>
      </Pane>
    </section>
  )
}
