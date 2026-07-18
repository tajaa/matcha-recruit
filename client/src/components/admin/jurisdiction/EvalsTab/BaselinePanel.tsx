import { useEffect, useState } from 'react'
import { api } from '../../../../api/client'
import { ChecklistByCategory } from './ChecklistByCategory'
import { scoreColor } from './helpers'
import type { BaselineJurisdiction } from './types'

export function BaselinePanel() {
  const [data, setData] = useState<BaselineJurisdiction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<{ jurisdictions: BaselineJurisdiction[] }>('/admin/jurisdictions/evals/baseline-checklist')
      .then((r) => setData(r.jurisdictions))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }, [])

  if (error) return <p className="text-xs text-red-400">{error}</p>
  if (!data) return <p className="text-xs text-zinc-500">Loading…</p>

  return (
    <div className="space-y-4">
      <p className="text-xs text-zinc-500">
        The enumerated federal + CA-state labor obligations a general employer owes, scored against
        each base jurisdiction's own catalog. Every miss is a gap carrying the citation to research
        next — the checkable answer to "is federal/state actually done?".
      </p>
      {data.map((jur) => (
        <div key={jur.label} className="border border-zinc-800 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-zinc-200">{jur.label}</p>
            <p className={`text-sm font-bold ${scoreColor(jur.score)}`}>
              {jur.present}/{jur.expected}
            </p>
          </div>
          {!jur.jurisdiction_found && (
            <p className="text-[11px] text-amber-400 mb-2">No jurisdiction record found.</p>
          )}
          <ChecklistByCategory
            items={jur.items}
            linkFor={(i) => ({
              href: i.authority_url,
              title: `${i.citation}${i.applies_note ? ' — ' + i.applies_note : ''}`,
            })}
          />
        </div>
      ))}
    </div>
  )
}
