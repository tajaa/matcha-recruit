import { BAND_TONE, renewalBand } from '../../utils/broker/brokerFormat'

/** Days-to-renewal countdown badge. Extracted alongside DeltaPill so Book of
 *  Business + Action Center share it. `derived` marks a date inferred from a
 *  Limit Adequacy coverage-line expiry rather than broker-confirmed. */
export function RenewalPill({ days, derived }: { days: number | null; derived?: boolean }) {
  if (days === null) return <span className="text-zinc-700 text-[10px]">—</span>

  const band = renewalBand(days)
  const label = band === 'expired' ? 'Expired' : `${days}d`

  const toneClass =
    band === 'expired' || band === 'critical' ? `${BAND_TONE.critical.text} ${BAND_TONE.critical.bg} border rounded px-1.5 py-0.5`
    : band === 'warning' ? `${BAND_TONE.fair.text} ${BAND_TONE.fair.bg} border rounded px-1.5 py-0.5`
    : BAND_TONE.unknown.text

  return (
    <span
      className={`inline-flex items-center text-[10px] font-mono ${toneClass} ${derived ? 'italic' : ''}`}
      title={derived ? 'From coverage-line expiry — not broker-confirmed' : undefined}
    >
      {label}
    </span>
  )
}

export default RenewalPill
