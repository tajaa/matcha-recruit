import { useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion } from '../hooks'
import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { DISPLAY, HILITE, INK, PAPER, hexA } from '../theme'
import { FORECAST_TOTAL, laborByRole, laborCost } from '../weekData'
import { StepHead } from './Chrome'

const ROLES = laborByRole(true)
const TOTAL = laborCost(true).total
const SWATCH = [HILITE, hexA(HILITE, 0.55), hexA(PAPER, 0.72), hexA(PAPER, 0.38)]
const money = (n: number) => `$${Math.round(n).toLocaleString('en-US')}`

/** Counts up to `value` once, the first time it's seen. */
function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const seen = useInView(ref, '0px 0px -15% 0px', 0.5)
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (!seen || reduced) return
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 1500)
      setShown(value * (1 - Math.pow(1 - t, 3)))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, reduced, value])
  return (
    <span ref={ref} aria-label={money(value)} style={{ fontVariantNumeric: 'tabular-nums' }}>
      <span aria-hidden>{money(reduced ? value : shown)}</span>
    </span>
  )
}

export function Cost() {
  const pct = ((TOTAL / FORECAST_TOTAL) * 100).toFixed(1)
  return (
    <section id="cost" className="sched-dark" style={{ backgroundColor: INK, color: PAPER }}>
      <div className={`${WRAP} grid grid-cols-1 gap-14 py-24 sm:py-36 lg:grid-cols-12 lg:gap-12`}>
        <div className="lg:col-span-5">
          <StepHead step="cost" dark title="Know what the week costs before it’s posted.">
            Every shift is priced from the pay rate on file, with weekly and California daily overtime applied. Anyone without a rate shows as
            unpriced — never as $0, so a missing number can’t make the week look cheaper than it is.
          </StepHead>
        </div>

        <div className="lg:col-span-7 lg:pl-6">
          <Reveal>
            <div style={mono('10.5px', { color: hexA(PAPER, 0.6) })}>Scheduled labor · week of Oct 5</div>
            <div className="mt-6" style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 'clamp(5rem, 13vw, 11rem)', lineHeight: 0.86, letterSpacing: '-0.01em' }}>
              <CountUp value={TOTAL} />
            </div>
            <div className="mt-6 flex flex-wrap gap-x-8 gap-y-2" style={mono('11px', { color: hexA(PAPER, 0.75) })}>
              <span>
                <span style={{ color: HILITE }}>{pct}%</span> of forecast sales
              </span>
              <span>
                <span style={{ color: HILITE }}>$0</span> overtime
              </span>
              <span>
                <span style={{ color: HILITE }}>+12h</span> unpriced
              </span>
            </div>
          </Reveal>

          <Reveal delay={150} className="mt-12">
            <div className="grow-x flex h-4 gap-[2px] overflow-hidden rounded-[3px]" role="img" aria-label="Labor cost by role" style={{ ['--d' as string]: '250ms' }}>
              {ROLES.map((r, i) => (
                <span key={r.role} className="h-full" style={{ width: `${(r.cost / TOTAL) * 100}%`, backgroundColor: SWATCH[i] }} />
              ))}
            </div>
            <table className="mt-8 w-full border-collapse" style={mono('11px', { color: PAPER })}>
              <thead>
                <tr style={{ color: hexA(PAPER, 0.5) }}>
                  <th className="pb-3 text-left font-normal">Role</th>
                  <th className="pb-3 text-right font-normal">People</th>
                  <th className="pb-3 text-right font-normal">Hours</th>
                  <th className="pb-3 text-right font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {ROLES.map((r, i) => (
                  <tr key={r.role} style={{ borderTop: `1px solid ${hexA(PAPER, 0.14)}` }}>
                    <td className="py-3">
                      <span className="mr-2.5 inline-block h-2.5 w-2.5 rounded-[1px] align-middle" style={{ backgroundColor: SWATCH[i] }} />
                      {r.role}
                    </td>
                    <td className="py-3 text-right">{r.people}</td>
                    <td className="py-3 text-right">{r.hours}h</td>
                    <td className="py-3 text-right">{money(r.cost)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px dashed ${hexA(PAPER, 0.3)}`, color: hexA(PAPER, 0.55) }}>
                  <td className="py-3">
                    <span className="mr-2.5 inline-block h-2.5 w-2.5 rounded-[1px] align-middle" style={{ border: `1px dashed ${hexA(PAPER, 0.5)}` }} />
                    Prep · new hire
                  </td>
                  <td className="py-3 text-right">1</td>
                  <td className="py-3 text-right">12h</td>
                  <td className="py-3 text-right" style={{ color: HILITE }}>
                    Unpriced
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="mt-6 text-[0.85rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.5) }}>
              No pay rate on file for the new hire, so their hours are listed, not guessed.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
