import { useEffect, useState } from 'react'
import { api } from '../../../../api/client'
import type { GoldenResponse } from './types'

export function GoldenPanel() {
  const [data, setData] = useState<GoldenResponse | null>(null)

  useEffect(() => {
    api.get<GoldenResponse>('/admin/jurisdictions/evals/golden').then(setData).catch(() => {})
  }, [])

  if (!data) return <p className="text-sm text-zinc-600">Loading golden facts…</p>

  const stateCls: Record<string, string> = {
    active: 'text-emerald-400',
    pending: 'text-zinc-500',
    expired: 'text-red-400',
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-4 text-xs text-zinc-400">
        <span><strong className="text-zinc-200">{data.total}</strong> facts</span>
        <span><strong className="text-emerald-400">{data.active}</strong> active today</span>
        <span>
          <strong className={data.unverified ? 'text-amber-400' : 'text-zinc-200'}>{data.unverified}</strong>{' '}
          awaiting human verification
        </span>
      </div>
      {data.unverified > 0 && (
        <p className="text-xs text-amber-400/80 border border-amber-500/30 rounded px-3 py-2">
          Unverified facts are asserted against the catalog but were drafted, not confirmed against the
          primary source by a human. Verify them before trusting the accuracy subscore.
        </p>
      )}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/50">
            <tr>
              {['State', 'Jurisdiction', 'Key', 'Comparator', 'Window', 'Source', 'Verified'].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.facts.map((f) => (
              <tr key={`${f.jurisdiction}-${f.requirement_key}-${f.effective_from}`} className="border-t border-zinc-900">
                <td className={`px-3 py-2 font-medium ${stateCls[f.state]}`}>{f.state}</td>
                <td className="px-3 py-2 text-zinc-400">{f.jurisdiction}</td>
                <td className="px-3 py-2 text-zinc-300 font-mono">{f.requirement_key}</td>
                <td className="px-3 py-2 text-zinc-500">{f.comparator}</td>
                <td className="px-3 py-2 text-zinc-500">
                  {f.effective_from} → {f.effective_to || '∞'}
                </td>
                <td className="px-3 py-2">
                  <a href={f.authority_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
                    source
                  </a>
                </td>
                <td className="px-3 py-2 text-zinc-500">{f.verified_by || <span className="text-amber-400">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
