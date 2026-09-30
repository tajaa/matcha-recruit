import { AlertTriangle, Plane, ShieldCheck, Ticket } from 'lucide-react'
import type { AgentFlightOption, AgentFlightSlice, AgentFlights } from '../../../api/matchaWork'
import {
  dayOffset, flightClock, flightDay, flightDuration, stopsText,
} from '../../../utils/flightFormat'
import { formatMoney } from '../../../utils/money'

/**
 * A flight-search result on an agent card (server: agent_card/flights.py).
 * Every price, time, flight number, bag and warning shown here is the
 * server's own search data; the agent only chose the offers and wrote the
 * label and reasons.
 */

function SliceRow({ slice }: { slice: AgentFlightSlice }) {
  const plusDays = dayOffset(slice.departing_at, slice.arriving_at)
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
      <span className="w-24 shrink-0 text-w-dim">{flightDay(slice.departing_at)}</span>
      <span className="font-medium text-w-text">
        {flightClock(slice.departing_at)} {slice.origin}
        <span className="mx-1 text-w-faint">→</span>
        {flightClock(slice.arriving_at)} {slice.destination}
        {plusDays > 0 && <sup className="ml-0.5 text-[10px] text-amber-300">+{plusDays}</sup>}
      </span>
      <span className="text-w-dim">
        {[flightDuration(slice.duration_minutes), stopsText(slice.stops)].filter(Boolean).join(' · ')}
        {slice.stops > 0 && ` via ${slice.segments.slice(0, -1).map((s) => s.destination).join(', ')}`}
      </span>
      <span className="font-mono text-[11px] text-w-faint">
        {slice.segments.map((s) => s.flight_number).join(', ')}
      </span>
    </div>
  )
}

function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'good' | 'warn' }) {
  const tones = {
    neutral: 'border-w-line text-w-dim',
    good: 'border-emerald-500/40 text-emerald-300',
    warn: 'border-amber-500/40 text-amber-300',
  }
  return <span className={`rounded-full border px-1.5 py-0.5 text-[10px] ${tones[tone]}`}>{children}</span>
}

function OptionCard({ option }: { option: AgentFlightOption }) {
  const withBags = option.true_total_amount && option.true_total_amount !== option.total_amount
  const { changeable, refundable } = option.conditions
  return (
    <div className="space-y-2 rounded-xl border border-w-line bg-w-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {option.label && (
              <span className="rounded-md bg-w-accent/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-w-accent">
                {option.label}
              </span>
            )}
            <span className="text-sm font-semibold text-w-text">{option.carriers.join(' + ') || 'Flight'}</span>
            {option.ticketing === 'separate' && (
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                <Ticket className="h-3 w-3" /> 2 tickets
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {changeable != null && <Chip tone={changeable ? 'good' : 'warn'}>{changeable ? 'Changeable' : 'No changes'}</Chip>}
            {refundable != null && <Chip tone={refundable ? 'good' : 'neutral'}>{refundable ? 'Refundable' : 'Non-refundable'}</Chip>}
            <Chip>
              {option.bags_included.checked
                ? `${option.bags_included.checked} checked bag incl.`
                : 'No checked bag incl.'}
            </Chip>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-lg font-bold text-w-text">
            {formatMoney(withBags ? option.true_total_amount : option.total_amount, option.currency)}
          </p>
          {withBags && (
            <p className="text-[10px] text-w-dim">fare {formatMoney(option.total_amount, option.currency)} + bags</p>
          )}
          {option.bag_note && <p className="max-w-[160px] text-[10px] text-w-faint">{option.bag_note}</p>}
        </div>
      </div>
      <div className="space-y-1 border-t border-w-line pt-2">
        {option.slices.map((slice, i) => <SliceRow key={`${slice.departing_at}-${i}`} slice={slice} />)}
      </div>
      {option.why.length > 0 && (
        <ul className="space-y-0.5 text-xs text-w-text">
          {option.why.map((reason) => <li key={reason}>• {reason}</li>)}
        </ul>
      )}
      {option.warnings.length > 0 && (
        <ul className="space-y-0.5">
          {option.warnings.map((warning) => (
            <li key={warning} className="flex gap-1.5 text-[11px] text-amber-300">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function searchedAt(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function AgentFlightsView({ flights }: { flights: AgentFlights }) {
  const when = searchedAt(flights.searched_at)
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Plane className="h-4 w-4 text-w-accent" />
        <p className="text-xs font-medium text-w-text">{flights.query_summary}</p>
        {flights.test_data && (
          <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[9px] font-bold tracking-wider text-orange-300">
            TEST DATA · NOT REAL FARES
          </span>
        )}
      </div>
      {flights.options.map((option) => <OptionCard key={option.id} option={option} />)}
      <p className="text-[11px] text-w-faint">
        {when ? `Prices as of ${when}. ` : ''}Fares change fast; run the card again to refresh them.
      </p>
      <div className="flex gap-2 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-2.5 text-[11px] text-w-dim">
        <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
        <div className="space-y-0.5">
          <p className="font-medium text-emerald-300">Searched privately, via {flights.privacy.via}</p>
          <p>Sent: {flights.privacy.sent.join(', ')}.</p>
          <p>Not sent: {flights.privacy.not_sent.join(', ')}.</p>
        </div>
      </div>
    </div>
  )
}
