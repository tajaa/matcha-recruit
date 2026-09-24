import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useInView, useReducedMotion } from '../hooks'
import { CountUp, Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { AMBER, CARD, INK, INK_SOFT, RED_PEN, STAMP, hexA } from '../theme'
import { Accent, CellLabel, StepHead } from './Chrome'

/** Saturday, 6a–11p: committed sales per hour (relative) and the people the
 *  draft puts on the floor for it. Same Saturday as the hero. */
const SALES = [2, 5, 9, 10, 8, 7, 9, 10, 8, 6, 5, 5, 6, 7, 6, 4, 3, 2]
const PEOPLE = [2, 3, 4, 4, 4, 3, 4, 4, 4, 3, 3, 3, 3, 3, 3, 2, 2, 2]

const RULE = hexA(INK, 0.1)

const clock = (i: number) => {
  const h = 6 + i
  return h === 12 ? '12p' : h > 12 ? `${h - 12}p` : `${h}a`
}

/** Hours step forward on their own once the chart is on screen: a playhead
 *  walks the day and reads out sales and headcount for the hour under it. */
function useWalk(length: number, start: number, ms: number) {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useInView(ref, '0px 0px -10% 0px', 0.4)
  const reduced = useReducedMotion()
  const [i, setI] = useState(start)
  useEffect(() => {
    if (!seen || reduced) return
    let timer = 0
    const wait = window.setTimeout(() => {
      timer = window.setInterval(() => setI((x) => (x + 1) % length), ms)
    }, 1400)
    return () => {
      window.clearTimeout(wait)
      window.clearInterval(timer)
    }
  }, [seen, reduced, length, ms])
  return { ref, i }
}

function SalesChart() {
  const W = 640
  const H = 168
  const bw = W / SALES.length
  const maxS = 10
  const maxP = 5
  const y = (p: number) => H - (p / maxP) * H
  const step = PEOPLE.map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * bw} ${y(p)} L ${(i + 1) * bw} ${y(p)}`).join(' ')
  const { ref, i: hour } = useWalk(SALES.length, 7, 700)
  return (
    <div ref={ref}>
      {/* live readout for the hour under the playhead */}
      <div className="mb-4 flex items-baseline justify-between" style={mono('10px', { color: INK_SOFT })}>
        <span>
          <span style={{ color: INK }}>{clock(hour)}</span> · ${SALES[hour] * 68} in sales
        </span>
        <span>
          <span style={{ color: INK }}>{PEOPLE[hour]}</span> on the floor
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full overflow-visible" aria-hidden>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={0} x2={W} y1={H * f} y2={H * f} stroke={hexA(INK, 0.06)} strokeWidth={1} />
        ))}
        {SALES.map((v, i) => (
          <rect
            key={i}
            className="grow-bar"
            x={i * bw + bw * 0.28}
            y={H - (v / maxS) * H}
            width={bw * 0.44}
            height={(v / maxS) * H}
            rx={bw * 0.22}
            fill={i === hour ? INK : v >= 9 ? STAMP : hexA(INK, 0.14)}
            style={{ ['--d' as string]: `${i * 30}ms`, transition: 'fill .35s ease, transform .8s cubic-bezier(.2,.7,.2,1) var(--d, 0ms)' }}
          />
        ))}
        <path className="pen-draw" d={step} fill="none" stroke={INK} strokeWidth={1.25} strokeLinejoin="round" pathLength={1} style={{ ['--d' as string]: '700ms' }} />
        {/* playhead */}
        <line
          x1={0}
          x2={0}
          y1={-6}
          y2={H}
          stroke={hexA(INK, 0.35)}
          strokeWidth={1}
          strokeDasharray="2 3"
          style={{ transform: `translateX(${(hour + 0.5) * bw}px)`, transition: 'transform .5s cubic-bezier(.4,0,.2,1)' }}
        />
        <circle r={3.5} fill={INK} style={{ transform: `translate(${(hour + 0.5) * bw}px, ${y(PEOPLE[hour])}px)`, transition: 'transform .5s cubic-bezier(.4,0,.2,1)' }} />
        <line x1={0} x2={W} y1={H} y2={H} stroke={hexA(INK, 0.2)} strokeWidth={1} />
      </svg>
      <div className="mt-3 flex justify-between" style={mono('10px', { color: INK_SOFT })}>
        <span>6a</span>
        <span>12p</span>
        <span>6p</span>
        <span>11p</span>
      </div>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-1" style={mono('10px', { color: INK_SOFT })}>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: STAMP }} /> Rush hours
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: hexA(INK, 0.2) }} /> Sales / hr
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-px w-4" style={{ backgroundColor: INK, boxShadow: `0 0 0 0.5px ${INK}` }} /> People on the floor
        </span>
      </div>
    </div>
  )
}

const WEEK = [
  { d: 'Mon', t: 66 },
  { d: 'Tue', t: 64 },
  { d: 'Wed', t: 67 },
  { d: 'Thu', t: 69 },
  { d: 'Fri', t: 71 },
  { d: 'Sat', t: 74 },
  { d: 'Sun', t: 70 },
]

function Weather() {
  return (
    <div>
      <div className="flex items-end justify-between gap-6">
        <div className="text-[clamp(4.5rem,8vw,6.5rem)] font-normal leading-[0.85] tracking-[-0.05em]" style={{ color: INK }}>
          <CountUp value={74} from={58} format={(n) => `${n}°`} />
        </div>
        <div className="pb-2 text-right" style={mono('10px', { color: INK_SOFT })}>
          Sat Oct 10
          <br />
          Sunny · 0% rain
        </div>
      </div>
      <div className="mt-8 grid grid-cols-7 gap-1.5">
        {WEEK.map((w, i) => {
          const sat = w.d === 'Sat'
          return (
            <div key={w.d} className="flex flex-col items-center gap-2">
              <div className="flex h-14 w-full items-end justify-center">
                {/* the warm day is the one to staff for: amber */}
                <div
                  className="grow-bar w-1.5 rounded-full"
                  style={{ height: `${(w.t - 58) * 3.4}px`, backgroundColor: sat ? AMBER : hexA(INK, 0.16), ['--d' as string]: `${300 + i * 70}ms` }}
                />
              </div>
              <span style={mono('9.5px', { color: sat ? INK : INK_SOFT, fontWeight: sat ? 700 : 400 })}>{w.d}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-6 flex items-center gap-2" style={mono('10px', { color: STAMP, fontWeight: 700 })}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STAMP }} />
        Sat · +1 on the floor, 12p–8p
      </div>
    </div>
  )
}

type Cell = 'open' | 'blocked' | 'off'
const AVAIL: { name: string; days: Cell[] }[] = [
  { name: 'Priya S.', days: ['open', 'open', 'open', 'blocked', 'open', 'open', 'open'] },
  { name: 'Theo K.', days: ['open', 'open', 'open', 'off', 'open', 'open', 'blocked'] },
  { name: 'Sam O.', days: ['blocked', 'open', 'open', 'open', 'open', 'open', 'open'] },
]

function Availability() {
  return (
    <div>
      <div className="grid grid-cols-[72px_repeat(7,minmax(0,1fr))] items-center gap-x-1.5 gap-y-2.5">
        <span />
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
          <span key={i} className="text-center" style={mono('9.5px', { color: INK_SOFT })}>
            {d}
          </span>
        ))}
        {AVAIL.map((row, r) => (
          <Row key={row.name} name={row.name} days={row.days} r={r} />
        ))}
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2" style={mono('10px', { color: INK_SOFT })}>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2 w-4 rounded-full" style={{ backgroundColor: hexA(INK, 0.07) }} /> Free
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2 w-4 rounded-full" style={{ backgroundColor: INK }} /> Blocked
        </span>
        <span className="inline-flex items-center gap-2" style={{ color: AMBER }}>
          <span className="pulse-dot h-1.5 w-1.5 rounded-full" style={{ backgroundColor: AMBER }} /> 1 request waiting
        </span>
      </div>
    </div>
  )
}

function Row({ name, days, r }: { name: string; days: Cell[]; r: number }) {
  return (
    <>
      <span className="truncate text-[13px] font-medium" style={{ color: INK }}>
        {name}
      </span>
      {days.map((d, i) => (
        <span
          key={i}
          className={`cell-in flex h-7 items-center justify-center rounded-full ${d === 'off' ? 'pulse-ring' : ''}`}
          style={{
            backgroundColor: d === 'open' ? hexA(INK, 0.07) : INK,
            ['--d' as string]: `${(r * 7 + i) * 35 + 200}ms`,
            ...mono('8.5px', { color: CARD, letterSpacing: '0.08em' }),
          }}
        >
          {d === 'off' ? 'Off' : ''}
        </span>
      ))}
    </>
  )
}

const CERTS = [
  { who: 'Theo K.', what: 'Food handler card', status: 'Current to Mar 2027', ok: true },
  { who: 'Ana R.', what: 'Shift lead', status: 'Qualified', ok: true },
  { who: 'Kiko T.', what: 'Food handler card', status: 'Expired Aug 30', ok: false },
]

function Certs() {
  return (
    <div>
      <ul>
        {CERTS.map((c, i) => (
          <li
            key={c.who + c.what}
            className="row-in flex items-center gap-4 py-4"
            style={{ borderBottom: `1px solid ${RULE}`, ['--d' as string]: `${300 + i * 140}ms` }}
          >
            <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c.ok ? STAMP : RED_PEN }} aria-hidden />
            <span className="min-w-0 flex-1 truncate text-[15px]" style={{ color: INK }}>
              <span className="font-medium">{c.who}</span> <span style={{ color: INK_SOFT }}>{c.what}</span>
            </span>
            <span className="shrink-0" style={mono('10px', { color: c.ok ? INK_SOFT : RED_PEN })}>
              {c.status}
            </span>
          </li>
        ))}
      </ul>
      <div className="row-in mt-5" style={{ ...mono('10px', { color: INK_SOFT }), ['--d' as string]: '800ms' }}>
        Kiko stays off cook shifts until renewed
      </div>
    </div>
  )
}

/** One of the four inputs: a numbered label, the copy, then the evidence.
 *  No card chrome — the grid's hairlines do the separating. */
function Input({ n, tag, title, body, children, className = '', delay }: { n: string; tag: string; title: string; body: string; children: ReactNode; className?: string; delay: number }) {
  return (
    <Reveal delay={delay} className={`flex flex-col py-12 sm:py-14 ${className}`} style={{ borderColor: RULE }}>
      <CellLabel n={n}>{tag}</CellLabel>
      <h3 className="mt-5 text-[1.45rem] font-medium leading-tight tracking-[-0.025em]" style={{ color: INK }}>
        {title}
      </h3>
      <p className="mt-2 max-w-[26rem] text-[0.97rem] leading-[1.6]" style={{ color: INK_SOFT }}>
        {body}
      </p>
      <div className="mt-10 flex flex-1 flex-col justify-end">{children}</div>
    </Reveal>
  )
}

export function Draft() {
  return (
    <section id="draft" className={`${WRAP} py-28 sm:py-44`}>
      <StepHead
        split
        step="draft"
        title={
          <>
            It starts from what you <Accent>already know.</Accent>
          </>
        }
      >
        The draft reads four things Matcha already has about your store and builds a week that fits all of them at once.
      </StepHead>
      {/* hairline 2×2: rules between cells, none around the outside */}
      <div className="mt-16 grid grid-cols-1 lg:grid-cols-2" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
        <Input n="01" tag="Sales" delay={0} className="lg:border-r lg:pr-14" title="What you sold, by the hour" body="Committed sales from past weeks set how many people each part of the day needs.">
          <SalesChart />
        </Input>
        <Input n="02" tag="Weather" delay={120} className="border-t lg:border-t-0 lg:pl-14" title="What the week will feel like" body="The forecast for your store’s address. A warm Saturday gets another person before the rush, not after it.">
          <Weather />
        </Input>
        <Input n="03" tag="Availability" delay={0} className="border-t lg:border-r lg:pr-14" title="Who said they can’t" body="Recurring availability, approved time off, and open requests. Nobody lands on a day they blocked.">
          <Availability />
        </Input>
        <Input n="04" tag="Jobs" delay={120} className="border-t lg:pl-14" title="Who can do the work" body="Shifts only go to people qualified for the job, with certifications that are current on the day.">
          <Certs />
        </Input>
      </div>
    </section>
  )
}
