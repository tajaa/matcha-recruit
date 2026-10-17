import { AdminButton as Button, AdminSelect, AdminTable } from '../../AdminUI'
import { useState } from 'react'
import { api } from '../../../../api/client'

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
        <AdminSelect
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warn">Warn</option>
          <option value="info">Info</option>
        </AdminSelect>
        <AdminSelect
          value={suite}
          onChange={(e) => setSuite(e.target.value)}
        >
          <option value="">All suites</option>
          {SUITES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </AdminSelect>
        <span className="text-xs text-zinc-500 self-center">
          showing {rows.length} of {detail.total}
        </span>
      </div>

      <AdminTable>
        <thead >
          <tr>
            {['Severity', 'Type', 'Jurisdiction', 'Key', 'Detail', ''].map((h) => (
              <th key={h} className="text-left text-zinc-500">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.id} className="border-t border-zinc-900">
              <td >{severityBadge(f.severity)}</td>
              <td className="text-zinc-300 whitespace-nowrap">{f.finding_type}</td>
              <td className="text-zinc-400 whitespace-nowrap">{f.jurisdiction_label || '—'}</td>
              <td className="text-zinc-400 font-mono">{f.requirement_key || '—'}</td>
              <td className="text-zinc-500 max-w-md truncate">
                {f.observed ? JSON.stringify(f.observed) : '—'}
              </td>
              <td className="whitespace-nowrap">
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
              <td colSpan={6} className="text-center text-zinc-600">No findings match.</td>
            </tr>
          )}
        </tbody>
      </AdminTable>
    </div>
  )
}
