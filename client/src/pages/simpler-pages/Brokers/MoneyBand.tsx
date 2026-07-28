import { AMBER, ASH, BONE, LEAF, LINE_D, SURFACE } from '../../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'
import { BOOK_MONEY } from './data'

// ── Money — the page's biggest gap before this pass: not one dollar figure
// anywhere. These three are the product's own strongest money statements
// (IRPremiumImpactCard's Premium Impact Estimate, the Insurance tab's Est.
// commission, the Loss Triangle's adverse development), shown as one
// illustrative sample book with the product's own caveat carried verbatim.
// No loss-ratio constant, no mod-sensitivity rule, no factor weights — the
// outputs, not the mechanics. ──────────────────────────────────────────────

const CARDS = [
  {
    label: 'Premium Δ',
    value: BOOK_MONEY.premiumDelta,
    sub: BOOK_MONEY.premiumDeltaSub,
    color: '#ff8a75',
  },
  {
    label: 'Est. commission',
    value: BOOK_MONEY.commission,
    sub: BOOK_MONEY.commissionSub,
    color: LEAF,
  },
  {
    label: 'Adverse development',
    value: BOOK_MONEY.adverseDev,
    sub: BOOK_MONEY.adverseDevSub,
    color: AMBER,
  },
]

export function MoneyBand() {
  return (
    <section className={SECTION_Y}>
      <div className={CONTAINER}>
        <Reveal>
          <div className={EYEBROW} style={{ color: ASH, marginBottom: '1rem' }}>
            What it's worth
          </div>
          <h2
            className="tracking-tight max-w-lg"
            style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: BONE, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.08 }}
          >
            The number that moves the renewal.
          </h2>

          <div className="mt-10 grid sm:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE_D }}>
            {CARDS.map((c) => (
              <div key={c.label} className="p-7" style={{ backgroundColor: SURFACE }}>
                <div className="text-[10.5px] font-mk-mono uppercase tracking-[0.2em] mb-3" style={{ color: ASH }}>
                  {c.label}
                </div>
                <div className="text-[2.25rem] tabular-nums" style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: c.color, lineHeight: 1 }}>
                  {c.value}
                </div>
                <div className="mt-2 text-[13px]" style={{ color: ASH }}>
                  {c.sub}
                </div>
              </div>
            ))}
          </div>

          <p className="mt-5 text-[12px]" style={{ color: ASH, opacity: 0.75 }}>
            {BOOK_MONEY.caveat}
          </p>
        </Reveal>
      </div>
    </section>
  )
}
