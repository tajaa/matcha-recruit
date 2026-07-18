import type { ReactNode } from 'react'
import { classificationLabel } from './constants'
import type { LogEntry, Summary300A } from './types'

// Exact export content, rendered inside the attestation modal so the reviewer
// sees every field that will leave the system — including Description (Column
// F), the name-cleansed field — before they sign off.
export function renderLogPreview(entries: LogEntry[], year: number): ReactNode {
  if (entries.length === 0) {
    return <p className="text-[12px] text-zinc-500">No OSHA-recordable rows for {year}.</p>
  }
  return (
    <table className="w-full text-left text-[11px]">
      <thead className="text-zinc-500">
        <tr>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Case #</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Employee</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Title</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Date</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Location</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Class</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold text-right">Away</th>
          <th className="py-1.5 pr-3 uppercase tracking-widest font-bold text-right">Restr.</th>
          <th className="py-1.5 uppercase tracking-widest font-bold">Description (Col. F)</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={`${e.incident_id}-${e.case_number}`} className="border-t border-white/5 text-zinc-300 align-top">
            <td className="py-1.5 pr-3 font-mono text-zinc-500">{e.case_number}</td>
            <td className="py-1.5 pr-3 text-zinc-100">
              {e.is_privacy_case ? 'Privacy Case' : e.employee_name}
            </td>
            <td className="py-1.5 pr-3 text-zinc-400">{e.job_title || '—'}</td>
            <td className="py-1.5 pr-3 font-mono text-zinc-400">{e.date_of_injury}</td>
            <td className="py-1.5 pr-3 text-zinc-400">{e.location || '—'}</td>
            <td className="py-1.5 pr-3 text-zinc-400">
              {e.classification ? classificationLabel[e.classification] ?? e.classification : '—'}
            </td>
            <td className="py-1.5 pr-3 text-right font-mono text-zinc-300">{e.days_away || '—'}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-zinc-300">{e.days_restricted || '—'}</td>
            <td className="py-1.5 text-zinc-300">{e.description || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function render300aPreview(summary: Summary300A | null): ReactNode {
  if (!summary) return null
  const rows: [string, string | number][] = [
    ['Establishment', summary.establishment_name || '—'],
    ['Total Cases', summary.total_cases],
    ['Deaths', summary.total_deaths],
    ['Days-Away Cases', summary.total_days_away_cases],
    ['Restricted/Transfer Cases', summary.total_restricted_cases],
    ['Other Recordable Cases', summary.total_other_recordable],
    ['Total Days Away', summary.total_days_away],
    ['Total Days Restricted', summary.total_days_restricted],
    ['Injuries', summary.total_injuries],
    ['Skin Disorders', summary.total_skin_disorders],
    ['Respiratory Conditions', summary.total_respiratory],
    ['Poisonings', summary.total_poisonings],
    ['Hearing Loss', summary.total_hearing_loss],
    ['Other Illnesses', summary.total_other_illnesses],
    ['Avg. Employees', summary.average_employees ?? '—'],
    ['Total Hours Worked', summary.total_hours_worked ?? '—'],
    ['Certified By', summary.certified_by || '—'],
    ['Certified Title', summary.certified_title || '—'],
    ['Certified Date', summary.certified_date || '—'],
  ]
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12px]">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between border-b border-white/5 pb-1">
          <dt className="text-zinc-500">{k}</dt>
          <dd className="text-zinc-200 font-mono">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

// ITA spans every active establishment (this panel loads one location's 300A
// at a time), so the modal points the reviewer at the per-establishment 300A
// rather than re-aggregating all of them here.
export function renderItaPreview(year: number): ReactNode {
  return (
    <p className="text-[12px] text-zinc-400 leading-relaxed">
      The ITA file rolls up the 300A totals for every active establishment for {year}.
      Review each establishment's 300A (switch the location selector above) before exporting —
      the export uses the same figures shown there.
    </p>
  )
}
