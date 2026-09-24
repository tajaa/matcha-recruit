import { useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion } from '../hooks'
import { Reveal } from '../motion'
import { WRAP, mono } from '../styles'
import { BOARD, PAPER, hexA } from '../theme'
import { FORECAST_TOTAL, laborByRole, laborCost } from '../weekData'
import { CellLabel, StepHead } from './Chrome'

const ROLES = laborByRole(true)
const TOTAL = laborCost(true).total
// Grayscale by share of cost, largest in full ink — the Draft chart's rule.
const SWATCH = [PAPER, hexA(PAPER, 0.55), hexA(PAPER, 0.32), hexA(PAPER, 0.16)]
const RULE = hexA(PAPER, 0.1)
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
    // Same flat dark gray as the hero: the Draft section, inverted.
    <section id="cost" className="sched-dark" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <div className={`${WRAP} py-28 sm:py-44`}>
        <StepHead split step="cost" dark title="Know what the week costs before it’s posted.">
          Every shift is priced from the pay rate on file, with weekly and California daily overtime applied. Anyone without a rate shows as
          unpriced — never as $0, so a missing number can’t make the week look cheaper than it is.
        </StepHead>

        <div className="mt-16 grid grid-cols-1 lg:grid-cols-2" style={{ borderTop: `1px solid ${RULE}`, borderBottom: `1px solid ${RULE}` }}>
          <Reveal className="flex flex-col py-12 lg:border-r lg:pr-14" style={{ borderColor: RULE }}>
            <CellLabel n="01" dark>Scheduled labor · week of Oct 5</CellLabel>
            <div className="mt-8 text-[clamp(4.5rem,10vw,8.5rem)] font-normal leading-[0.85] tracking-[-0.05em]" style={{ color: PAPER }}>
              <CountUp value={TOTAL} />
            </div>
            <dl className="mt-auto grid grid-cols-3 items-end gap-6 pt-12">
              {[
                { k: 'Of sales', v: `${pct}%` },
                { k: 'Overtime', v: '$0' },
                { k: 'Unpriced', v: '12h' },
              ].map((x) => (
                <div key={x.k}>
                  <dt style={mono('10px', { color: hexA(PAPER, 0.55) })}>{x.k}</dt>
                  <dd className="mt-2 text-[1.9rem] font-normal leading-none tracking-[-0.04em]" style={{ color: PAPER, fontVariantNumeric: 'tabular-nums' }}>
                    {x.v}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>

          <Reveal delay={120} className="flex flex-col border-t py-12 lg:border-t-0 lg:pl-14" style={{ borderColor: RULE }}>
            <CellLabel n="02" dark>By role</CellLabel>
            <div className="grow-x mt-8 flex h-2 gap-[3px]" role="img" aria-label="Labor cost by role" style={{ ['--d' as string]: '250ms' }}>
              {ROLES.map((r, i) => (
                <span key={r.role} className="h-full rounded-full" style={{ width: `${(r.cost / TOTAL) * 100}%`, backgroundColor: SWATCH[i] }} />
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
                  <tr key={r.role} style={{ borderTop: `1px solid ${RULE}` }}>
                    <td className="py-3.5">
                      <span className="mr-3 inline-block h-1.5 w-4 rounded-full align-middle" style={{ backgroundColor: SWATCH[i] }} />
                      {r.role}
                    </td>
                    <td className="py-3.5 text-right">{r.people}</td>
                    <td className="py-3.5 text-right">{r.hours}h</td>
                    <td className="py-3.5 text-right">{money(r.cost)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px solid ${RULE}`, color: hexA(PAPER, 0.55) }}>
                  <td className="py-3.5">
                    <span className="mr-3 inline-block h-1.5 w-4 rounded-full align-middle" style={{ boxShadow: `inset 0 0 0 1px ${hexA(PAPER, 0.4)}` }} />
                    Prep · new hire
                  </td>
                  <td className="py-3.5 text-right">1</td>
                  <td className="py-3.5 text-right">12h</td>
                  <td className="py-3.5 text-right" style={{ color: PAPER }}>
                    Unpriced
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="mt-6 text-[0.9rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.55) }}>
              No pay rate on file for the new hire, so their hours are listed, not guessed.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
