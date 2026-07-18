import { Eye, EyeOff, Loader2, Lock } from 'lucide-react'
import { Button } from '../../ui'
import { privacyReasonLabel } from './constants'
import type { LogEntry, PrivacyCaseRow } from './types'

interface PrivacyCaseListProps {
  canRevealNames: boolean
  entries: LogEntry[]
  privacyNames: PrivacyCaseRow[] | null
  setPrivacyNames: (rows: PrivacyCaseRow[] | null) => void
  revealConfidentialNames: () => void
  revealing: boolean
}

// Confidential privacy-case reference list (admin/client only). OSHA
// masks the name on the public log; this resolves case # → real name
// (29 CFR 1904.29(b)(9)). Every reveal is audit-logged server-side.
export function PrivacyCaseList({
  canRevealNames,
  entries,
  privacyNames,
  setPrivacyNames,
  revealConfidentialNames,
  revealing,
}: PrivacyCaseListProps) {
  if (!canRevealNames || !entries.some((e) => e.is_privacy_case)) return null
  return (
    <div className="bg-zinc-900/40 border border-amber-500/20 rounded-lg p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Lock size={14} className="text-amber-400" />
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            Confidential Privacy-Case Names
          </span>
        </div>
        {privacyNames === null ? (
          <Button size="sm" variant="ghost" onClick={revealConfidentialNames} disabled={revealing}>
            {revealing ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Eye size={12} className="mr-1.5" />}
            Reveal names
          </Button>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setPrivacyNames(null)}>
            <EyeOff size={12} className="mr-1.5" />
            Hide
          </Button>
        )}
      </div>
      {privacyNames !== null &&
        (privacyNames.length === 0 ? (
          <p className="text-[12px] text-zinc-500 mt-3">No privacy-case names to show.</p>
        ) : (
          <table className="w-full text-sm text-left mt-3">
            <thead className="text-zinc-500">
              <tr>
                <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Case #</th>
                <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Employee</th>
                <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Reason</th>
              </tr>
            </thead>
            <tbody>
              {privacyNames.map((p) => (
                <tr key={p.incident_id} className="border-t border-white/5 text-zinc-300">
                  <td className="py-2 font-mono text-[11px] text-zinc-500">{p.case_number}</td>
                  <td className="py-2 text-[13px] text-zinc-100">{p.real_employee_name}</td>
                  <td className="py-2 text-[12px] text-zinc-400">
                    {p.privacy_case_reason ? privacyReasonLabel[p.privacy_case_reason] ?? p.privacy_case_reason : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </div>
  )
}
