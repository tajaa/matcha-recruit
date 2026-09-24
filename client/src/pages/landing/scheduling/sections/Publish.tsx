import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { CARD, DISPLAY, HILITE, INK, INK_SOFT, PAPER, RED_PEN, STAMP, hexA } from '../theme'
import { StepHead } from './Chrome'

// Jonah's week after both of the page's edits: the hero moved Dev's Friday
// open to him, the chat moved Dev's Tuesday open to him — 40h, no overtime.
const JONAH = [
  { day: 'Mon 5', time: '2p–10p', isNew: false },
  { day: 'Tue 6', time: '7a–3p', isNew: true },
  { day: 'Wed 7', time: '7a–3p', isNew: false },
  { day: 'Fri 9', time: '6a–2p', isNew: true },
  { day: 'Sat 10', time: '10a–6p', isNew: false, swap: true },
]

const REQUESTS = [
  { kind: 'Swap', who: 'Jonah B.', what: 'Sat 10a–6p ↔ Sam’s 7a–3p', note: 'Both qualified · hours unchanged' },
  { kind: 'Time off', who: 'Kiko T.', what: 'Oct 14–16', note: 'No published shifts affected' },
  { kind: 'Availability', who: 'Sam O.', what: 'No Tuesdays from Nov 1', note: 'Takes effect on an unpublished week' },
]

function Phone() {
  return (
    <div className="relative mx-auto w-full max-w-[300px]">
      {/* push notification, arriving over the phone */}
      <div
        className="toast-in absolute -left-4 -right-4 -top-10 z-10 rounded-2xl px-4 py-3 sm:-left-12 sm:-right-12"
        style={{ backgroundColor: hexA(CARD, 0.94), backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', boxShadow: `0 0 0 1px ${hexA(INK, 0.08)}, 0 24px 40px -20px ${hexA(INK, 0.5)}` }}
      >
        <div className="flex items-center justify-between" style={mono('9px', { color: INK_SOFT })}>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-flex h-4 w-4 items-center justify-center rounded-[4px] text-[9px] font-bold" style={{ backgroundColor: STAMP, color: PAPER }}>
              m
            </span>
            Matcha
          </span>
          <span>now</span>
        </div>
        <div className="mt-1.5 text-[14px] font-semibold" style={{ color: INK }}>
          Your week at Juniper Café is posted
        </div>
        <div className="text-[13px]" style={{ color: INK_SOFT }}>
          5 shifts · 40h · 2 new
        </div>
      </div>

      <div className="rounded-[46px] p-[10px]" style={{ backgroundColor: INK, boxShadow: `0 40px 70px -40px ${hexA(INK, 0.4)}` }}>
        <div className="relative overflow-hidden rounded-[37px]" style={{ backgroundColor: CARD, aspectRatio: '9 / 18.5' }}>
          <div className="absolute left-1/2 top-2.5 h-[22px] w-[88px] -translate-x-1/2 rounded-full" style={{ backgroundColor: INK }} />
          <div className="flex h-full flex-col px-5 pb-5 pt-12">
            <div className="flex items-baseline justify-between" style={mono('9px', { color: INK_SOFT })}>
              <span>Juniper Café</span>
              <span>Week 41</span>
            </div>
            <div className="mt-1" style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 38, lineHeight: 0.9, textTransform: 'uppercase', color: INK }}>
              My week
            </div>
            <ul className="mt-4 space-y-2">
              {JONAH.map((s) => (
                <li key={s.day} className="rounded-lg px-3 py-2.5" style={{ backgroundColor: '#fff', border: `1px solid ${s.swap ? hexA(RED_PEN, 0.5) : hexA(INK, 0.1)}` }}>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold" style={{ color: INK }}>
                      {s.day}
                    </span>
                    {s.isNew && (
                      <span className="rounded-sm px-1 py-px" style={mono('8.5px', { backgroundColor: HILITE, color: INK, fontWeight: 700 })}>
                        New
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center justify-between" style={mono('9.5px', { color: INK_SOFT })}>
                    <span>{s.time} · Barista</span>
                    {s.swap && <span style={{ color: RED_PEN }}>Swap asked</span>}
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-auto flex items-center justify-between pt-3" style={mono('9.5px', { color: INK })}>
              <span>40h this week</span>
              <span className="rounded-full px-2.5 py-1" style={{ backgroundColor: INK, color: PAPER }}>
                Request
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function Publish() {
  return (
    <section id="publish" className={`${WRAP} grid grid-cols-1 gap-16 py-28 sm:py-44 lg:grid-cols-12 lg:items-center lg:gap-12`}>
      <Reveal className="order-2 lg:order-1 lg:col-span-5">
        <Phone />
      </Reveal>
      <div className="order-1 lg:order-2 lg:col-span-6 lg:col-start-7">
        <StepHead step="publish" title="Publish. It’s on their phone.">
          Published shifts land in each person’s portal the moment you post. Swaps, drops, time off, and availability changes come back to you
          as requests — approve one and the schedule updates, deny it and nothing moves.
        </StepHead>
        <Reveal delay={200} className="mt-12">
          <div className="flex items-baseline justify-between pb-3" style={{ ...mono('10.5px', { color: INK_SOFT }), borderBottom: `1.5px solid ${INK}` }}>
            <span>Waiting on you</span>
            <span>3</span>
          </div>
          <ul>
            {REQUESTS.map((r) => (
              <li key={r.kind} className="flex items-center justify-between gap-4 py-4" style={{ borderBottom: `1px solid ${hexA(INK, 0.08)}` }}>
                <span className="min-w-0">
                  <span style={mono('9.5px', { color: INK_SOFT })}>{r.kind}</span>
                  <span className="mt-0.5 block text-[16px] font-semibold" style={{ color: INK }}>
                    {r.who} <span style={{ fontWeight: 400 }}>· {r.what}</span>
                  </span>
                  <span className="mt-0.5 block text-[13px]" style={{ color: STAMP }}>
                    ✓ {r.note}
                  </span>
                </span>
                <span className="flex shrink-0 gap-2">
                  <span className="hidden rounded-full px-3 py-1.5 text-[13px] sm:inline" style={{ border: `1px solid ${hexA(INK, 0.25)}`, color: INK }}>
                    Deny
                  </span>
                  <span className="rounded-full px-3 py-1.5 text-[13px] font-semibold" style={{ backgroundColor: STAMP, color: PAPER }}>
                    Approve
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  )
}
