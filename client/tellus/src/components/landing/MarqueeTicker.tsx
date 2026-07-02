// Illustrative example redemptions only — not real/live data. Reuses the
// "Corner Coffee Co." placeholder already used in the hero ticket rather
// than inventing new brand-sounding names.
const TICKER_ITEMS = [
  { label: 'Corner Coffee Co.', pts: '140' },
  { label: 'Riverside Books', pts: '85' },
  { label: 'Sunset Diner', pts: '210' },
  { label: 'The Print Shop', pts: '60' },
  { label: 'Maple Street Bakery', pts: '175' },
]

function Row() {
  return (
    <div className="flex shrink-0 items-center gap-10 px-5" aria-hidden>
      {TICKER_ITEMS.map((t, i) => (
        <span key={i} className="flex items-center gap-1.5 font-mono text-[11px] tracking-wide text-tu-ink/55">
          <span aria-hidden>🎟</span> +<span className="font-bold text-tu-accent">{t.pts}</span> pts · {t.label}
        </span>
      ))}
    </div>
  )
}

// Reads as a strip of receipt tape — same tu-paper/tu-ink material as the hero ticket.
export function MarqueeTicker() {
  return (
    <div className="overflow-hidden border-y border-tu-border bg-tu-paper py-2.5">
      <span className="sr-only">Example redemptions (illustrative)</span>
      <div className="tu-marquee-track flex w-max">
        <Row />
        <Row />
      </div>
    </div>
  )
}
