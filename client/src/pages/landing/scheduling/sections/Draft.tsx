import type { ReactNode } from 'react'
import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { CARD, DISPLAY, HILITE, INK, INK_SOFT, RED_PEN, STAMP, hexA } from '../theme'
import { Accent, StepHead } from './Chrome'

/** Saturday, 6a–11p: committed sales per hour (relative) and the people the
 *  draft puts on the floor for it. Same Saturday as the hero. */
const SALES = [2, 5, 9, 10, 8, 7, 9, 10, 8, 6, 5, 5, 6, 7, 6, 4, 3, 2]
const PEOPLE = [2, 3, 4, 4, 4, 3, 4, 4, 4, 3, 3, 3, 3, 3, 3, 2, 2, 2]

function SalesChart() {
  const W = 640
  const H = 180
  const bw = W / SALES.length
  const maxS = 10
  const maxP = 5
  const step = PEOPLE.map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * bw} ${H - (p / maxP) * H} L ${(i + 1) * bw} ${H - (p / maxP) * H}`).join(' ')
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full overflow-visible">
        {SALES.map((v, i) => (
          <rect
            key={i}
            className="grow-bar"
            x={i * bw + 3}
            y={H - (v / maxS) * H}
            width={bw - 6}
            height={(v / maxS) * H}
            rx={2}
            fill={v >= 9 ? STAMP : hexA(INK, 0.16)}
            style={{ ['--d' as string]: `${i * 35}ms` }}
          />
        ))}
        <path className="pen-draw" d={step} fill="none" stroke={RED_PEN} strokeWidth={3} strokeLinejoin="round" pathLength={1} style={{ ['--d' as string]: '700ms' }} />
      </svg>
      <div className="mt-2 flex justify-between" style={mono('9.5px', { color: INK_SOFT })}>
        <span>6a</span>
        <span>12p</span>
        <span>6p</span>
        <span>11p</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1" style={mono('9.5px', { color: INK_SOFT })}>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-[1px]" style={{ backgroundColor: STAMP }} /> Sales / hr
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-[2px] w-4" style={{ backgroundColor: RED_PEN }} /> People on the floor
        </span>
      </div>
    </div>
  )
}

function Weather() {
  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 100 100" className="h-[104px] w-[104px] shrink-0" aria-hidden>
        <g className="sun-rays">
          {Array.from({ length: 12 }, (_, i) => (
            <line key={i} x1="50" y1="6" x2="50" y2="18" stroke={INK} strokeWidth="3" strokeLinecap="round" transform={`rotate(${i * 30} 50 50)`} />
          ))}
        </g>
        <circle cx="50" cy="50" r="22" fill={HILITE} stroke={INK} strokeWidth="3" />
      </svg>
      <div>
        <div style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 'clamp(4.4rem, 7vw, 6rem)', lineHeight: 0.8, color: INK }}>74°</div>
        <div className="mt-3" style={mono('10px', { color: INK_SOFT })}>
          Sat Oct 10 · sunny
        </div>
        <div className="mt-2 inline-block rounded-sm px-1.5 py-0.5" style={mono('10px', { backgroundColor: HILITE, color: INK, fontWeight: 700 })}>
          +1 on the floor · 12p–8p
        </div>
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
      <div className="grid grid-cols-[76px_repeat(7,minmax(0,1fr))] gap-1.5" style={mono('9.5px', { color: INK_SOFT })}>
        <span />
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
          <span key={i} className="text-center">
            {d}
          </span>
        ))}
        {AVAIL.map((row) => (
          <Row key={row.name} name={row.name} days={row.days} />
        ))}
      </div>
      <div className="mt-4 inline-flex items-center gap-2 rounded-full px-2.5 py-1" style={mono('9.5px', { color: INK, border: `1px solid ${hexA(INK, 0.25)}` })}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: RED_PEN }} />1 availability request waiting on you
      </div>
    </div>
  )
}

function Row({ name, days }: { name: string; days: Cell[] }) {
  return (
    <>
      <span className="self-center truncate normal-case" style={{ fontFamily: 'inherit', letterSpacing: 0, fontSize: 12.5, color: INK, fontWeight: 600 }}>
        {name}
      </span>
      {days.map((d, i) => (
        <span
          key={i}
          className="flex h-8 items-center justify-center rounded-[3px]"
          style={{
            border: `1px solid ${hexA(INK, d === 'open' ? 0.14 : 0.3)}`,
            backgroundColor: d === 'off' ? hexA(INK, 0.1) : 'transparent',
            backgroundImage: d === 'blocked' ? `repeating-linear-gradient(135deg, ${hexA(INK, 0.28)} 0 1.5px, transparent 1.5px 6px)` : undefined,
            color: INK,
            fontSize: 8.5,
          }}
        >
          {d === 'off' ? 'OFF' : ''}
        </span>
      ))}
    </>
  )
}

const CERTS = [
  { who: 'Theo K.', what: 'Food handler card', status: 'Current to Mar 2027', ok: true },
  { who: 'Ana R.', what: 'Shift lead', status: 'Qualified', ok: true },
  { who: 'Kiko T.', what: 'Food handler card', status: 'Expired Aug 30 · kept off cook shifts', ok: false },
]

function Certs() {
  return (
    <ul className="space-y-2.5">
      {CERTS.map((c) => (
        <li
          key={c.who + c.what}
          className="flex items-center gap-4 rounded-md px-4 py-3"
          style={{ backgroundColor: '#fff', border: `1px solid ${c.ok ? hexA(INK, 0.12) : hexA(RED_PEN, 0.55)}` }}
        >
          <span
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[14px] font-bold"
            style={{ backgroundColor: c.ok ? hexA(STAMP, 0.12) : hexA(RED_PEN, 0.1), color: c.ok ? STAMP : RED_PEN }}
            aria-hidden
          >
            {c.ok ? '✓' : '✕'}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold" style={{ color: INK }}>
              {c.who} <span style={{ fontWeight: 400, color: INK_SOFT }}>· {c.what}</span>
            </span>
            <span className="block truncate" style={mono('9.5px', { color: c.ok ? STAMP : RED_PEN, marginTop: 3 })}>
              {c.status}
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Specimen({ tag, title, body, children, className, delay }: { tag: string; title: string; body: string; children: ReactNode; className: string; delay: number }) {
  return (
    <Reveal
      delay={delay}
      className={`flex flex-col rounded-md p-6 sm:p-8 ${className}`}
      style={{ backgroundColor: CARD, border: `1px solid ${hexA(INK, 0.12)}`, boxShadow: `0 1px 0 ${hexA(INK, 0.04)}, 0 30px 50px -40px ${hexA(INK, 0.35)}` }}
    >
      <div className="flex items-center justify-between">
        <span className="rounded-sm px-1.5 py-0.5" style={mono('10px', { backgroundColor: HILITE, color: INK, fontWeight: 700 })}>
          {tag}
        </span>
        <span style={mono('9.5px', { color: INK_SOFT })}>Reads from Matcha</span>
      </div>
      <div className="my-8 flex min-h-[170px] flex-col justify-center">{children}</div>
      <div className="mt-auto border-t pt-5" style={{ borderColor: hexA(INK, 0.1) }}>
        <h3 className="text-[1.3rem] font-semibold leading-tight tracking-[-0.01em]" style={{ color: INK }}>
          {title}
        </h3>
        <p className="mt-2 text-[0.97rem] leading-[1.6]" style={{ color: INK_SOFT }}>
          {body}
        </p>
      </div>
    </Reveal>
  )
}

export function Draft() {
  return (
    <section id="draft" className={`${WRAP} py-28 sm:py-44`}>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <StepHead
            step="draft"
            title={
              <>
                It starts from what you <Accent>already know.</Accent>
              </>
            }
          >
            The draft reads four things Matcha already has about your store and builds a week that fits all of them at once.
          </StepHead>
        </div>
      </div>
      <div className="mt-16 grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Specimen className="lg:col-span-7" delay={0} tag="Sales" title="What you sold, by the hour" body="Committed sales from past weeks set how many people each part of the day needs.">
          <SalesChart />
        </Specimen>
        <Specimen className="lg:col-span-5" delay={120} tag="Weather" title="What the week will feel like" body="The forecast for your store’s address. A warm Saturday gets another person before the rush, not after it.">
          <Weather />
        </Specimen>
        <Specimen className="lg:col-span-5" delay={0} tag="Availability" title="Who said they can’t" body="Recurring availability, approved time off, and open requests. Nobody lands on a day they blocked.">
          <Availability />
        </Specimen>
        <Specimen className="lg:col-span-7" delay={120} tag="Jobs" title="Who can do the work" body="Shifts only go to people qualified for the job, with certifications that are current on the day.">
          <Certs />
        </Specimen>
      </div>
    </section>
  )
}
