import { useState } from 'react'
import { api } from '../../../../api/client'
import { Button } from '../../../ui'
import { SUITES } from './constants'
import { severityBadge } from './helpers'
import type { RunDetail } from './types'

export function FindingsTable({ detail, onResolved }: { detail: RunDetail; onResolved: () => void }) {
  const [severity, setSeverity] = useState('')
  const [suite, setSuite] = useState('')

  const rows = detail.findings.filter(
    (f) => (!severity || f.severity === severity) && (!suite || f.suite === suite),
  )

  const resolve = async (id: string, status: string) => {
    await api.post(`/admin/jurisdictions/evals/findings/${id}/resolve`, { status })
    onResolved()
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {detail.finding_counts.map((c) => (
          <span
            key={`${c.finding_type}-${c.severity}`}
            className="px-2 py-1 rounded border border-zinc-800 text-[11px] text-zinc-400"
          >
            {c.finding_type} {severityBadge(c.severity)} <strong className="text-zinc-200">{c.count}</strong>
          </span>
        ))}
      </div>

      <div className="flex gap-2">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warn">Warn</option>
          <option value="info">Info</option>
        </select>
        <select
          value={suite}
          onChange={(e) => setSuite(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200"
        >
          <option value="">All suites</option>
          {SUITES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="text-xs text-zinc-500 self-center">
          showing {rows.length} of {detail.total}
        </span>
      </div>

      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/50">
            <tr>
              {['Severity', 'Type', 'Jurisdiction', 'Key', 'Detail', ''].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id} className="border-t border-zinc-900">
                <td className="px-3 py-2">{severityBadge(f.severity)}</td>
                <td className="px-3 py-2 text-zinc-300 whitespace-nowrap">{f.finding_type}</td>
                <td className="px-3 py-2 text-zinc-400 whitespace-nowrap">{f.jurisdiction_label || '—'}</td>
                <td className="px-3 py-2 text-zinc-400 font-mono">{f.requirement_key || '—'}</td>
                <td className="px-3 py-2 text-zinc-500 max-w-md truncate">
                  {f.observed ? JSON.stringify(f.observed) : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {f.status === 'open' ? (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => resolve(f.id, 'confirmed')}>Confirm</Button>
                      <Button variant="ghost" size="sm" onClick={() => resolve(f.id, 'dismissed')}>Dismiss</Button>
                    </div>
                  ) : (
                    <span className="text-zinc-600">{f.status}</span>
                  )}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-zinc-600">No findings match.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
