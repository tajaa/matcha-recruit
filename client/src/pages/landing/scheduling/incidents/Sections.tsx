import type { CSSProperties, ReactNode } from 'react'
import { FileText, Lock } from 'lucide-react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, glassChip, glassPane, mono } from '../../../../components/marketing/kit/styles'
import { AMBER, BOARD, CARD, INK, INK_SOFT, PAPER, RED_PEN, SERIF, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, Glows, StepHead } from '../sections/Chrome'
import { CASE, DRIVE_PATH, FIRST_SECONDS, FLAG_THRESHOLD, MATCHES, NOTES, SIGNED_CHECKS, SIGNED_FILE, type NoteTone } from './data'

const ROW = 80 // ms between items ticking in
const NOTE_COLOR: Record<NoteTone, string> = { clear: STAMP, hr: AMBER, fix: RED_PEN }

/** Raised paper on paper: the letter, the phone screen, the scan. */
const raised: CSSProperties = {
  backgroundColor: CARD,
  boxShadow: `0 0 0 1px ${hexA(INK, 0.06)}, 0 1px 2px ${hexA(INK, 0.05)}, 0 40px 80px -48px ${hexA(INK, 0.45)}`,
}

function Dot({ color, className = '' }: { color: string; className?: string }) {
  return <span aria-hidden className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${className}`} style={{ backgroundColor: color }} />
}

/** A numbered marker tying a passage to its note. */
function Marker({ n, color }: { n: number; color: string }) {
  return (
    <span
      aria-label={`note ${n}`}
      className="mx-0.5 inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full align-[2px] text-[10px] font-semibold"
      style={{ backgroundColor: color, color: PAPER, fontFamily: 'inherit' }}
    >
      {n}
    </span>
  )
}

// ── 1 · Report ──────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={mono('8.5px', { color: INK_SOFT })}>{label}</div>
      <div className="mt-1.5 rounded-xl px-3 py-2.5 text-[13.5px] leading-[1.45]" style={{ backgroundColor: hexA(INK, 0.045), color: INK }}>
        {children}
      </div>
    </div>
  )
}

/** Ana's phone, the report filled in and just sent. */
function Phone() {
  return (
    <Reveal className="mx-auto w-full max-w-[300px]">
      <div className="rounded-[46px] p-[9px]" style={{ backgroundColor: INK, boxShadow: `0 50px 90px -46px ${hexA(INK, 0.7)}` }}>
        <div className="relative overflow-hidden rounded-[38px]" style={{ backgroundColor: CARD }}>
          <div className="flex items-center justify-between px-7 pt-3.5" style={mono('9px', { color: INK, letterSpacing: '0.04em' })}>
            <span>8:02</span>
            <span aria-hidden className="h-[18px] w-[76px] rounded-full" style={{ backgroundColor: INK }} />
            <span>5G</span>
          </div>
          <div className="space-y-3.5 px-5 pb-6 pt-5">
            <div>
              <div style={mono('8.5px', { color: INK_SOFT })}>Juniper Café · Downtown</div>
              <div className="mt-1 text-[19px] font-medium tracking-[-0.02em]" style={{ color: INK }}>
                Report an incident
              </div>
            </div>
            <Field label="What happened">Jonah missed his Tue, Thu and Sat opens. No call, no text. We covered the open each time.</Field>
            <div className="grid grid-cols-2 gap-2.5">
              <Field label="When">Tue · Thu · Sat</Field>
              <Field label="Where">Downtown</Field>
            </div>
            <Field label="Who was involved">
              <span className="inline-flex items-center gap-2">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-semibold" style={{ backgroundColor: INK, color: PAPER }}>
                  JB
                </span>
                Jonah B. · Barista
              </span>
            </Field>
            <div className="flex h-11 items-center justify-center rounded-full text-[14px] font-medium" style={{ backgroundColor: INK, color: PAPER }}>
              Submit report
            </div>
          </div>
          {/* the confirmation drops in once the phone is on screen */}
          <div
            className="toast-in absolute inset-x-3 top-10 flex items-center gap-2.5 rounded-2xl px-3.5 py-3"
            style={{ backgroundColor: hexA(CARD, 0.94), boxShadow: `0 0 0 1px ${hexA(INK, 0.08)}, 0 16px 34px -18px ${hexA(INK, 0.5)}`, backdropFilter: 'blur(10px)' }}
          >
            <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full" style={{ backgroundColor: STAMP }}>
              <svg width={12} height={12} viewBox="0 0 18 18" aria-hidden>
                <path d="M4 9.4 L7.6 12.6 L14 5.6" fill="none" stroke={PAPER} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold" style={{ color: INK }}>
                Report filed
              </span>
              <span className="block" style={mono('8.5px', { color: INK_SOFT, letterSpacing: '0.06em' })}>
                {CASE.incident}
              </span>
            </span>
          </div>
        </div>
      </div>
    </Reveal>
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
            Filed <Accent>from the floor.</Accent>
          </>
        }
      >
        Jonah missed three opens and never called. Ana, the shift lead, reports it from her phone between orders. Everything after that starts on
        its own.
      </StepHead>

      <div className="mt-16 grid grid-cols-1 items-center gap-14 lg:mt-20 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-5">
          <Phone />
        </div>
        <Reveal delay={120} className="lg:col-span-7">
          <CellLabel n="01">The first ten seconds</CellLabel>
          <ol className="relative mt-8 space-y-7 pl-7" style={{ borderLeft: `1px solid ${hexA(INK, 0.15)}` }}>
            {FIRST_SECONDS.map((s, i) => (
              <li key={s.title} className="relative">
                <span
                  aria-hidden
                  className="check-dot absolute -left-[32px] top-[7px] h-[9px] w-[9px] rounded-full"
                  style={{ ['--dot' as string]: i === FIRST_SECONDS.length - 1 ? RED_PEN : STAMP, ['--d' as string]: `${i * 260 + 300}ms`, boxShadow: `0 0 0 3px ${PAPER}` }}
                />
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-[1.15rem] font-medium tracking-[-0.02em]" style={{ color: INK }}>
                    {s.title}
                  </span>
                  {s.at && <span style={mono('10px', { color: INK_SOFT })}>{s.at}</span>}
                </div>
                <p className="mt-1 max-w-[32rem] text-[0.98rem] leading-[1.6]" style={{ color: INK_SOFT }}>
                  {s.body}
                </p>
              </li>
            ))}
          </ol>
          <p className="mt-10 max-w-[34rem] text-[0.9rem] leading-[1.6]" style={{ color: INK_SOFT }}>
            <span style={mono('9.5px', { color: INK })}>Anyone else</span>
            <br />
            Crew can report from a link with no login, or anonymously from the poster in the back room.
          </p>
        </Reveal>
      </div>
    </section>
  )
}

// ── 2 · Triage ──────────────────────────────────────────────────────────

/** A passage the check matched, with the number of the clause it matched. */
function Hit({ n, children }: { n: number; children: ReactNode }) {
  return (
    <>
      <mark
        className="rounded-[3px] px-0.5"
        style={{
          backgroundColor: hexA(RED_PEN, 0.13),
          color: INK,
          boxShadow: `inset 0 -1.5px 0 ${RED_PEN}`,
          WebkitBoxDecorationBreak: 'clone',
          boxDecorationBreak: 'clone',
        }}
      >
        {children}
      </mark>
      <Marker n={n} color={RED_PEN} />
    </>
  )
}

function Doc({ label, meta, children, delay = 0 }: { label: string; meta: string; children: ReactNode; delay?: number }) {
  return (
    <Reveal delay={delay} className="min-w-0 rounded-[22px] px-5 py-6 sm:px-7 sm:py-7" style={glassChip}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1" style={mono('9.5px', { color: INK_SOFT })}>
        <span style={{ color: INK }}>{label}</span>
        <span>{meta}</span>
      </div>
      <div className="mt-5 space-y-3.5 text-[1rem] leading-[1.7]" style={{ color: INK_SOFT }}>
        {children}
      </div>
    </Reveal>
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
            Read against <Accent>your</Accent> handbook.
          </>
        }
      >
        Matcha reads the report next to your own handbook and policies and points at the exact clause it breaks. It only reports. Whether a case opens
        is a fixed rule you can see and change.
      </StepHead>

      <div className="relative mt-16">
        <Glows green="14% 30%" amber="86% 70%" />
        <div className="relative rounded-[28px] p-2 sm:p-3" style={glassPane}>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            <Doc label="Incident" meta={CASE.incident}>
              <p style={{ color: INK }}>
                Jonah <Hit n={1}>missed his Tue, Thu and Sat opens</Hit>. <Hit n={2}>No call, no text.</Hit> We covered the open each time.
              </p>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 pt-3 sm:grid-cols-4" style={{ borderTop: `1px solid ${hexA(INK, 0.08)}` }}>
                {[
                  { k: 'Reported by', v: CASE.reporter },
                  { k: 'Involved', v: CASE.employee },
                  { k: 'Where', v: 'Downtown' },
                  { k: 'When', v: 'Tue · Thu · Sat' },
                ].map((x) => (
                  <div key={x.k}>
                    <dt style={mono('8.5px', { color: INK_SOFT })}>{x.k}</dt>
                    <dd className="mt-1 text-[0.9rem]" style={{ color: INK }}>
                      {x.v}
                    </dd>
                  </div>
                ))}
              </dl>
            </Doc>
            <Doc label="Handbook · Attendance and Punctuality" meta="Your policy" delay={120}>
              <p>
                <span style={{ color: INK }}>Reporting an absence.</span>{' '}
                <Hit n={2}>If you cannot work a scheduled shift you must notify your shift lead at least 2 hours before it starts.</Hit>
              </p>
              <p>
                <span style={{ color: INK }}>No-call/no-show.</span>{' '}
                <Hit n={1}>Three (3) no-call/no-shows within any rolling 30-day period is grounds for termination.</Hit>
              </p>
              <p>Absences protected by law are never counted under this policy.</p>
            </Doc>
          </div>

          {/* the decision: confidence against the line, and what it did */}
          <div className="mt-2 rounded-[22px] px-5 py-5 sm:px-7" style={glassChip}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1" style={mono('9.5px', { color: INK_SOFT })}>
              <span style={{ color: INK }}>Decision</span>
              <span>A case opens at {FLAG_THRESHOLD}%+ on a violated or bent policy</span>
            </div>
            <ol className="mt-4 space-y-4">
              {MATCHES.map((m, i) => (
                <Reveal key={m.policy} as="li" delay={i * ROW} className="grid grid-cols-1 gap-2.5 sm:grid-cols-12 sm:items-center sm:gap-6">
                  <div className="sm:col-span-4">
                    <div className="text-[0.98rem] font-medium tracking-[-0.015em]" style={{ color: INK }}>
                      {m.policy}
                    </div>
                    <div style={mono('9.5px', { color: m.opens ? RED_PEN : INK_SOFT })}>
                      {m.relevance} · {m.confidence}%
                    </div>
                  </div>
                  <div className="sm:col-span-5">
                    <div className="relative h-1.5 rounded-full" style={{ backgroundColor: hexA(INK, 0.08) }} role="img" aria-label={`${m.confidence}% confidence; a case opens at ${FLAG_THRESHOLD}%`}>
                      <div className="grow-x h-full rounded-full" style={{ width: `${m.confidence}%`, backgroundColor: m.opens ? RED_PEN : hexA(INK, 0.3), ['--d' as string]: `${i * ROW + 250}ms` }} />
                      <span aria-hidden className="absolute -top-1 h-3.5 w-px" style={{ left: `${FLAG_THRESHOLD}%`, backgroundColor: INK }} />
                    </div>
                  </div>
                  <div className="sm:col-span-3 sm:flex sm:justify-end">
                    <span className="inline-flex items-center gap-2 rounded-full px-2.5 py-1" style={{ ...mono('9px', { color: INK }), backgroundColor: hexA(m.opens ? RED_PEN : INK, m.opens ? 0.1 : 0.06) }}>
                      <Dot color={m.opens ? RED_PEN : hexA(INK, 0.4)} />
                      {m.opens ? `Opened ${CASE.number}` : 'Related · shown, not flagged'}
                    </span>
                  </div>
                </Reveal>
              ))}
            </ol>
          </div>

          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
            {[
              { t: 'Can’t check ≠ clean', d: 'A check that couldn’t run is recorded as unknown and opens nothing. It’s never read as a pass.' },
              { t: 'The story stays put', d: 'The case keeps policy names and confidence. Notices carry numbers and titles, never the narrative.' },
              { t: 'Closed stays closed', d: 'A case HR closed or dismissed is never reopened by a later check.' },
            ].map((x, i) => (
              <Reveal key={x.t} delay={200 + i * ROW} className="rounded-[22px] px-5 py-4" style={glassChip}>
                <div style={mono('9.5px', { color: INK })}>{x.t}</div>
                <p className="mt-1.5 text-[0.88rem] leading-[1.5]" style={{ color: INK_SOFT }}>
                  {x.d}
                </p>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

// ── 3 · Write-up ────────────────────────────────────────────────────────

const note = (n: number) => NOTES.find((x) => x.n === n)!

/** Ana's letter, as the review sees it: four layers, four margin notes. */
function Letter() {
  return (
    <Reveal className="relative rounded-[6px] px-5 py-8 sm:px-10 sm:py-12" style={raised}>
      {/* note 1: the leave check's stamp */}
      <div
        className="mb-5 inline-flex rotate-[2deg] items-center rounded-md px-2.5 py-1.5 sm:absolute sm:right-8 sm:top-8 sm:mb-0 sm:rotate-[4deg]"
        style={{ ...mono('9px', { color: STAMP, fontWeight: 600 }), boxShadow: `inset 0 0 0 1.5px ${STAMP}` }}
      >
        Leave check · clear <Marker n={1} color={NOTE_COLOR[note(1).tone]} />
      </div>

      <div className="sm:pr-48">
        <div className="text-[15px] font-semibold tracking-[-0.01em]" style={{ color: INK }}>
          Juniper Café
        </div>
        <div className="mt-1" style={mono('9.5px', { color: INK_SOFT })}>
          Written warning · Attendance <Marker n={2} color={NOTE_COLOR[note(2).tone]} />
        </div>
      </div>

      <div className="mt-7 space-y-4 text-[0.95rem] leading-[1.7]" style={{ color: INK }}>
        <p style={{ color: INK_SOFT }}>October 6, 2026 · To: {CASE.employeeFull}, Barista</p>
        <p>
          On Tuesday September 8, Thursday September 17 and Saturday September 26 you missed your scheduled opening shift without notifying your shift
          lead.{' '}
          <span className="relative">
            <del style={{ color: INK_SOFT, textDecorationColor: RED_PEN, textDecorationThickness: 2 }}>You are always late and you don’t care about the team.</del>
            <Marker n={3} color={NOTE_COLOR[note(3).tone]} />
          </span>
        </p>
        <p>Under the Attendance and Punctuality policy, three no-call/no-shows within 30 days is grounds for termination.</p>
        <p>
          <span style={mono('9.5px', { color: INK_SOFT })}>Expectation</span>
          <br />
          From today, tell your shift lead at least 2 hours before any shift you can’t work.
        </p>
        <p>
          <span style={mono('9.5px', { color: INK_SOFT })}>Consequence</span>
          <br />
          Another no-call/no-show may lead to further discipline, up to termination.
        </p>
      </div>

      <div className="mt-9 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <div className="h-px" style={{ backgroundColor: hexA(INK, 0.35) }} />
          <div className="mt-2" style={mono('9px', { color: INK_SOFT })}>
            Ana R. · Shift lead
          </div>
        </div>
        <div className="flex items-center justify-between gap-2 rounded-md px-3 py-2.5" style={{ boxShadow: `inset 0 0 0 1.5px ${RED_PEN}`, backgroundImage: `repeating-linear-gradient(135deg, ${hexA(RED_PEN, 0.06)} 0 6px, transparent 6px 12px)` }}>
          <span style={mono('9px', { color: RED_PEN, fontWeight: 600 })}>Employee signature — missing</span>
          <Marker n={4} color={NOTE_COLOR[note(4).tone]} />
        </div>
      </div>
    </Reveal>
  )
}

/** Tue 8:40 AM — the letter, reviewed before HR sees it. */
export function WriteUp() {
  return (
    <section id="writeup" className={`${WRAP} pb-28 sm:pb-44`}>
      <StepHead
        split
        step="writeup"
        title={
          <>
            Red-penned <Accent>before</Accent> HR reads it.
          </>
        }
      >
        Ana sends the letter as an upload, a Drive file, or a Google Doc link. It’s filed in HR’s Drive and reviewed in four layers. Ana sees only
        what she can fix. The leave findings stay with HR.
      </StepHead>

      <div className="mt-16 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-7">
          <Letter />
        </div>
        <ol className="space-y-3 lg:col-span-5">
          {NOTES.map((x, i) => (
            <Reveal key={x.n} as="li" delay={i * ROW} className="flex gap-4 rounded-[20px] px-5 py-4" style={glassChip}>
              <Marker n={x.n} color={NOTE_COLOR[x.tone]} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="text-[0.98rem] font-medium tracking-[-0.015em]" style={{ color: INK }}>
                    {x.title}
                  </span>
                  <span style={mono('9px', { color: INK_SOFT })}>{x.layer}</span>
                </div>
                <p className="mt-1 text-[0.9rem] leading-[1.55]" style={{ color: INK_SOFT }}>
                  {x.body}
                </p>
              </div>
            </Reveal>
          ))}
          <Reveal as="li" delay={NOTES.length * ROW} className="flex flex-wrap gap-x-5 gap-y-2 px-2 pt-2" style={mono('9px', { color: INK_SOFT })}>
            <span className="inline-flex items-center gap-2">
              <Dot color={RED_PEN} /> Ana fixes
            </span>
            <span className="inline-flex items-center gap-2">
              <Dot color={AMBER} /> Waits on HR
            </span>
            <span className="inline-flex items-center gap-2">
              <Dot color={STAMP} /> Clear
            </span>
          </Reveal>
        </ol>
      </div>
    </section>
  )
}

// ── 4 · Approve (dark) ─────────────────────────────────────────────────

const RULE = hexA(PAPER, 0.1)
const DIM = hexA(PAPER, 0.6)

function Screen({ who, title, children, delay = 0 }: { who: string; title: string; children: ReactNode; delay?: number }) {
  return (
    <Reveal delay={delay} className="min-w-0 rounded-[22px] p-5 sm:p-7" style={{ backgroundColor: BOARD.CARD, boxShadow: `inset 0 0 0 1px ${hexA(PAPER, 0.08)}` }}>
      <div style={mono('9.5px', { color: DIM })}>{who}</div>
      <div className="mt-2 text-[1.2rem] font-medium tracking-[-0.02em]" style={{ color: PAPER }}>
        {title}
      </div>
      {children}
    </Reveal>
  )
}

function Line({ dot, k, v }: { dot: string; k: string; v: string }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] items-baseline gap-3 py-3 sm:grid-cols-[9rem_1fr]" style={{ borderTop: `1px solid ${RULE}` }}>
      <span className="inline-flex items-center gap-2" style={mono('9px', { color: DIM })}>
        <Dot color={dot} />
        {k}
      </span>
      <span className="text-[0.92rem] leading-[1.5]" style={{ color: PAPER }}>
        {v}
      </span>
    </div>
  )
}

/** Tue 9:15 AM — HR decides, and sees more than the manager does. */
export function Approve() {
  return (
    <section id="approve" className="sched-dark" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <div className={`${WRAP} py-28 sm:py-44`}>
        <StepHead split step="approve" dark title="HR decides. Ana sees what she needs.">
          HR reads the letter next to everything the review found and approves it or sends it back with a reason. Leave records can change after the review,
          so the protected-leave check runs again the moment HR approves.
        </StepHead>

        <div className="mt-16 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Screen who="HR · Case HRC-2026-0001" title="Written warning · Jonah B.">
            <div className="mt-5">
              <Line dot={BOARD.RED_PEN} k="Handbook" v="Attendance and Punctuality · violated, 98%" />
              <Line dot={BOARD.STAMP} k="Leave" v="Clear · runs again when you approve" />
              <Line dot={BOARD.AMBER} k="History" v="Skips a step · no warning in 12 months" />
              <Line dot={BOARD.STAMP} k="Letter" v="Two notes, both fixed by Ana" />
            </div>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <span className="inline-flex h-10 items-center rounded-full px-5 text-[14px] font-medium" style={{ backgroundColor: PAPER, color: BOARD.PAPER }}>
                Approve
              </span>
              <span className="inline-flex h-10 items-center rounded-full px-5 text-[14px] font-medium" style={{ boxShadow: `inset 0 0 0 1px ${hexA(PAPER, 0.35)}`, color: PAPER }}>
                Send back
              </span>
            </div>
            <div className="mt-4 rounded-xl px-3.5 py-3" style={{ backgroundColor: hexA(PAPER, 0.05), boxShadow: `inset 0 0 0 1px ${RULE}` }}>
              <div className="text-[0.88rem]" style={{ color: DIM }}>
                Why it’s going back…
              </div>
              <div className="mt-2" style={mono('8.5px', { color: hexA(PAPER, 0.45) })}>
                20 characters minimum · Ana sees this
              </div>
            </div>
          </Screen>

          <Screen who="Ana · Write-ups" title="Jonah B. · written warning" delay={120}>
            <div className="mt-5 flex items-center justify-between gap-3 rounded-xl px-3.5 py-3" style={{ backgroundColor: hexA(BOARD.STAMP, 0.12) }}>
              <span className="inline-flex items-center gap-2 text-[0.95rem] font-medium" style={{ color: PAPER }}>
                <Dot color={BOARD.STAMP} /> Approved · deliver it
              </span>
              <span style={mono('9px', { color: DIM })}>9:15 AM</span>
            </div>
            <div className="mt-3">
              <Line dot={BOARD.STAMP} k="Your notes" v="Two, both fixed" />
            </div>
            <div className="mt-4" style={mono('9px', { color: DIM })}>
              Not shown to Ana
            </div>
            <ul className="mt-2.5 space-y-2">
              {['Leave findings', 'Handbook matches', 'Jonah’s earlier cases'].map((x, i) => (
                <li key={x} className="flex items-center gap-3 rounded-xl px-3.5 py-2.5" style={{ backgroundColor: hexA(PAPER, 0.04) }}>
                  <Lock size={13} aria-hidden style={{ color: DIM }} />
                  <span className="text-[0.88rem]" style={{ color: DIM }}>
                    {x}
                  </span>
                  <span aria-hidden className="ml-auto h-2 rounded-full" style={{ width: `${48 - i * 10}%`, maxWidth: 120, backgroundColor: hexA(PAPER, 0.09) }} />
                </li>
              ))}
            </ul>
          </Screen>
        </div>

        <div className="mt-10 grid grid-cols-1 sm:grid-cols-2" style={{ borderTop: `1px solid ${RULE}` }}>
          {[
            { at: 'Tue 9:15 AM', t: 'Approved to deliver', d: 'The leave check ran again from the same dates.' },
            { at: 'Tue 9:30 AM', t: 'Delivered', d: 'Ana hands Jonah the letter and marks it delivered.' },
          ].map((x, i) => (
            <Reveal key={x.t} delay={i * 120} className={`py-6 ${i ? 'sm:pl-10' : 'sm:pr-10'}`} style={i ? { borderTop: `1px solid ${RULE}` } : undefined}>
              <CellLabel n={`0${i + 1}`} dark>
                {x.at}
              </CellLabel>
              <div className="mt-4 text-[1.1rem] font-medium tracking-[-0.02em]" style={{ color: PAPER }}>
                {x.t}
              </div>
              <p className="mt-1 text-[0.92rem] leading-[1.55]" style={{ color: DIM }}>
                {x.d}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ── 5 · Signed ──────────────────────────────────────────────────────────

/** A region of the scan the check confirmed, ringed in green. */
function Ringed({ label, children, className = '', delay }: { label: string; children: ReactNode; className?: string; delay: number }) {
  return (
    <div className={`relative ${className}`}>
      <div className="ring-in rounded-md px-2 py-1.5" style={{ ['--d' as string]: `${delay}ms` }}>
        {children}
      </div>
      <span
        className="tag-in absolute -top-2.5 right-2 rounded-full px-2 py-0.5"
        style={{ ...mono('8px', { color: PAPER, fontWeight: 600 }), backgroundColor: STAMP, ['--d' as string]: `${delay + 120}ms` }}
      >
        {label}
      </span>
    </div>
  )
}

/** The signed copy as it came back: a phone photo of the page. */
function Scan() {
  return (
    <Reveal className="mx-auto w-full max-w-[520px]">
      <div className="-rotate-[1.4deg] rounded-[4px] px-5 py-7 sm:px-9 sm:py-10" style={{ ...raised, backgroundColor: '#F8F7F1' }}>
        <Ringed label="Right letter" delay={300}>
          <div className="text-[14px] font-semibold" style={{ color: INK }}>
            Juniper Café
          </div>
          <div style={mono('9px', { color: INK_SOFT })}>Written warning · Attendance · Oct 6, 2026</div>
        </Ringed>
        {/* the body, out of focus: the check reads it, the page doesn't need to */}
        <div aria-hidden className="mt-5 space-y-2.5 px-2">
          {[96, 88, 92, 54, 0, 90, 70, 0, 84, 62].map((w, i) =>
            w ? <div key={i} className="h-[7px] rounded-full" style={{ width: `${w}%`, backgroundColor: hexA(INK, 0.1) }} /> : <div key={i} className="h-2" />,
          )}
        </div>
        <div className="mt-7 grid grid-cols-2 gap-4">
          <Ringed label="Signed" delay={520}>
            <div className="text-[26px] leading-none sm:text-[32px]" style={{ fontFamily: SERIF, fontStyle: 'italic', color: '#1D3557' }}>
              Jonah Brooks
            </div>
            <div className="mt-2 h-px" style={{ backgroundColor: hexA(INK, 0.35) }} />
            <div className="mt-1.5" style={mono('8px', { color: INK_SOFT })}>
              Employee · Oct 7
            </div>
          </Ringed>
          <Ringed label="Signed" delay={640}>
            <div className="text-[26px] leading-none sm:text-[32px]" style={{ fontFamily: SERIF, fontStyle: 'italic', color: '#1D3557' }}>
              Ana R.
            </div>
            <div className="mt-2 h-px" style={{ backgroundColor: hexA(INK, 0.35) }} />
            <div className="mt-1.5" style={mono('8px', { color: INK_SOFT })}>
              Shift lead · Oct 7
            </div>
          </Ringed>
        </div>
        <div className="mt-5 flex justify-between gap-3">
          <Ringed label="Right person" delay={760}>
            <span style={mono('9px', { color: INK })}>Printed name: {CASE.employeeFull}</span>
          </Ringed>
          <span className="self-end" style={mono('8px', { color: INK_SOFT })}>
            1 / 1
          </span>
        </div>
      </div>
    </Reveal>
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
        Ana snaps the signed page with her phone. It’s filed straight away under Jonah’s name in HR’s Drive, then read to make sure it’s the letter HR
        approved, actually signed, by the right person. Then the case closes itself.
      </StepHead>

      <div className="mt-16 grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-6">
          <Scan />
        </div>
        <div className="space-y-3 lg:col-span-6">
          <Reveal className="rounded-[22px] px-5 py-5 sm:px-7" style={glassChip}>
            <div style={mono('9.5px', { color: INK_SOFT })}>Filed in Drive · Wed 2:28 PM</div>
            <div className="mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.92rem]" style={{ color: INK_SOFT }}>
              {DRIVE_PATH.map((p, i) => (
                <span key={p} className="inline-flex items-center gap-1.5">
                  {i > 0 && <span aria-hidden>›</span>}
                  <span style={i === DRIVE_PATH.length - 1 ? { color: INK, fontWeight: 500 } : undefined}>{p}</span>
                </span>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-3 rounded-xl px-3 py-2.5" style={{ backgroundColor: hexA(INK, 0.04) }}>
              <FileText size={16} aria-hidden style={{ color: INK_SOFT, flexShrink: 0 }} />
              <span className="min-w-0 break-all" style={mono('9.5px', { color: INK, letterSpacing: '0.03em', textTransform: 'none' })}>
                {SIGNED_FILE}
              </span>
            </div>
            <p className="mt-3 text-[0.85rem] leading-[1.5]" style={{ color: INK_SOFT }}>
              Named from your own filename template. The HR read is logged.
            </p>
          </Reveal>

          <Reveal delay={120} className="rounded-[22px] px-5 py-5 sm:px-7" style={glassChip}>
            <div style={mono('9.5px', { color: INK_SOFT })}>What the check read</div>
            <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              {SIGNED_CHECKS.map((c, i) => (
                <div key={c.k} className="flex gap-3">
                  <span
                    aria-hidden
                    className="check-dot mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ ['--dot' as string]: STAMP, ['--d' as string]: `${i * ROW + 400}ms` }}
                  />
                  <div>
                    <dt className="text-[0.95rem] font-medium" style={{ color: INK }}>
                      {c.k}
                    </dt>
                    <dd className="text-[0.88rem] leading-[1.45]" style={{ color: INK_SOFT }}>
                      {c.v}
                    </dd>
                  </div>
                </div>
              ))}
            </dl>
          </Reveal>

          <Reveal delay={240} className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] px-5 py-4 sm:px-7" style={{ backgroundColor: hexA(STAMP, 0.1), boxShadow: `inset 0 0 0 1px ${hexA(STAMP, 0.3)}` }}>
            <span className="inline-flex items-center gap-2.5 text-[0.98rem] font-medium" style={{ color: INK }}>
              <Dot color={STAMP} /> Verified · {CASE.number} closed
            </span>
            <span style={mono('9px', { color: INK_SOFT })}>Wed 2:30 PM</span>
          </Reveal>
          <p className="px-2 pt-1 text-[0.85rem] leading-[1.55]" style={{ color: INK_SOFT }}>
            A check that can’t run is never a pass, and anything Jonah writes on the page goes to HR only. Either way, the case waits for a person.
          </p>
        </div>
      </div>
    </section>
  )
}
