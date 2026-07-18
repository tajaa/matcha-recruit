import { Lock } from 'lucide-react'
import { Badge } from '../../ui'
import { classificationBadge, classificationLabel, privacyReasonLabel } from './constants'
import type { LogEntry } from './types'

interface Log300TableProps {
  entries: LogEntry[]
  year: number
  navigate: (path: string) => void
}

// 300 Log Table
export function Log300Table({ entries, year, navigate }: Log300TableProps) {
  return (
    <div className="bg-zinc-900/40 border border-white/[0.06] rounded-lg overflow-hidden">
      {entries.length === 0 ? (
        <div className="p-8 text-center">
          <p className="text-sm text-zinc-400">No OSHA-recordable incidents for {year}.</p>
          <p className="text-[11px] text-zinc-600 mt-1">Mark an incident OSHA recordable from its detail page.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-950/50 text-zinc-500">
              <tr>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Case #</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Employee</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Job Title</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Date</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Location</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Description</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Classification</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Days Away</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Days Restricted</th>
                <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Injury Type</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr
                  key={e.incident_id}
                  className="border-t border-white/5 text-zinc-300 hover:bg-white/[0.02] transition-colors cursor-pointer"
                  onClick={() => navigate(`/app/ir/${e.incident_id}`)}
                >
                  <td className="px-4 py-3 font-mono text-[11px] text-zinc-500">{e.case_number}</td>
                  <td className="px-4 py-3 text-[13px] text-zinc-100 font-medium">
                    {e.is_privacy_case ? (
                      <span className="inline-flex items-center gap-1.5">
                        <Lock size={11} className="text-amber-400 shrink-0" />
                        <span>Privacy Case</span>
                        {e.privacy_case_reason && (
                          <Badge variant="neutral">
                            {privacyReasonLabel[e.privacy_case_reason] ?? e.privacy_case_reason}
                          </Badge>
                        )}
                      </span>
                    ) : (
                      e.employee_name
                    )}
                  </td>
                  <td className="px-4 py-3 text-[12px] text-zinc-500">{e.job_title || '—'}</td>
                  <td className="px-4 py-3 text-[11px] text-zinc-400 font-mono">{e.date_of_injury}</td>
                  <td className="px-4 py-3 text-[12px] text-zinc-400">{e.location || '—'}</td>
                  <td className="px-4 py-3 text-[12px] text-zinc-400 max-w-[260px] truncate" title={e.description || ''}>
                    {e.description || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {e.classification ? (
                      <Badge variant={classificationBadge[e.classification] ?? 'neutral'}>
                        {classificationLabel[e.classification] ?? e.classification}
                      </Badge>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[12px] text-zinc-300">{e.days_away || '—'}</td>
                  <td className="px-4 py-3 text-right font-mono text-[12px] text-zinc-300">{e.days_restricted || '—'}</td>
                  <td className="px-4 py-3 text-[12px] text-zinc-500">{e.injury_type || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
