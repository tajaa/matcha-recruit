import { AlertTriangle, Check, CircleHelp, Loader2 } from 'lucide-react'
import type { HrCaseReadiness } from '../../../types'
import { thresholdPct } from './hrCaseGuide'

type Row = { state: 'ok' | 'problem' | 'unknown'; label: string; detail: string }

/** One row per thing that has to be true for a new incident to open a case.
 *  A source that couldn't be read is "unknown", never a pass. */
function setupRows(r: HrCaseReadiness): Row[] {
  const names = r.notified ?? []
  return [
    r.handbook_sources === null
      ? { state: 'unknown', label: 'Handbook and policies', detail: 'Couldn’t check right now.' }
      : r.handbook_sources > 0
        ? { state: 'ok', label: 'Handbook and policies', detail: `${r.handbook_sources} section${r.handbook_sources === 1 ? '' : 's'} on file to check incidents against.` }
        : { state: 'problem', label: 'Handbook and policies', detail: 'Nothing on file. Incidents are checked against your handbook, so none will be flagged until one is added.' },
    r.incidents_enabled === null
      ? { state: 'unknown', label: 'Incident reporting', detail: 'Couldn’t check right now.' }
      : r.incidents_enabled
        ? { state: 'ok', label: 'Incident reporting', detail: 'On. Every new incident is checked.' }
        : { state: 'problem', label: 'Incident reporting', detail: 'Off, so there are no incidents to check.' },
    r.notified === null
      ? { state: 'unknown', label: 'Who gets told', detail: 'Couldn’t check right now.' }
      : names.length
        ? { state: 'ok', label: 'Who gets told', detail: `${names.join(', ')} get a bell and an email when a case is flagged.` }
        : { state: 'problem', label: 'Who gets told', detail: 'No one with HR access would be notified. Give someone access to the HR / Discipline folder in Drive.' },
    { state: 'ok', label: 'Flag threshold', detail: `A case opens at ${thresholdPct(r.threshold)} confidence or higher.` },
  ]
}

const ICON = {
  ok: <Check size={14} className="text-emerald-400" />,
  problem: <AlertTriangle size={14} className="text-amber-400" />,
  unknown: <CircleHelp size={14} className="text-w-faint" />,
}

export default function SetupCheck({ readiness, loading, error }: { readiness: HrCaseReadiness | null; loading: boolean; error: boolean }) {
  if (loading) return <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-w-faint" /></div>
  if (error || !readiness) {
    return <p className="rounded-lg border border-w-line bg-w-surface2/40 px-3 py-2.5 text-xs text-w-dim">Couldn’t run the setup check right now. Cases will still open once an incident is flagged.</p>
  }
  return (
    <ul className="grid gap-2 md:grid-cols-2" aria-label="Setup check">
      {setupRows(readiness).map((row) => (
        <li key={row.label} className="flex gap-3 rounded-lg border border-w-line bg-w-surface2/40 px-3 py-2.5">
          <span className="mt-0.5 shrink-0" aria-label={row.state === 'ok' ? 'Ready' : row.state === 'problem' ? 'Needs attention' : 'Unknown'}>{ICON[row.state]}</span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-w-text">{row.label}</p>
            <p className="mt-0.5 text-xs leading-5 text-w-dim">{row.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  )
}
