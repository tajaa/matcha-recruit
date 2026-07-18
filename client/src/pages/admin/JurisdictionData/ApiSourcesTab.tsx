import { Fragment, useState } from 'react'
import { fmtDate } from '../../../components/admin/jurisdiction/utils'
import { getCategoryLabel, getShortLabel } from './helpers'
import type { ApiSourcesData } from './types'

interface ApiSourcesTabProps {
  data: ApiSourcesData | null
  loading: boolean
}

export default function ApiSourcesTab({ data, loading }: ApiSourcesTabProps) {
  const [expandedApiRow, setExpandedApiRow] = useState<string | null>(null)

  return (
    <div className="space-y-5">
      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : !data ? (
        <p className="text-sm text-zinc-600">Failed to load API sources data.</p>
      ) : (
        <>
          {/* Research source breakdown */}
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Requirements by Research Source</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {data.source_counts.map((s) => {
                const colors: Record<string, string> = {
                  official_api: 'text-emerald-400 border-emerald-500/30',
                  gemini: 'text-purple-400 border-purple-500/30',
                  claude_skill: 'text-blue-400 border-blue-500/30',
                  structured: 'text-amber-400 border-amber-500/30',
                  manual: 'text-zinc-300 border-zinc-600',
                  unknown: 'text-zinc-500 border-zinc-700',
                }
                const labels: Record<string, string> = {
                  official_api: 'Official APIs',
                  gemini: 'Gemini AI',
                  claude_skill: 'Claude Skill',
                  structured: 'Structured Data',
                  manual: 'Manual',
                  unknown: 'Untagged',
                }
                const color = colors[s.research_source] || colors.unknown
                return (
                  <div key={s.research_source} className={`border rounded-lg px-3 py-3 ${color}`}>
                    <p className="text-[10px] uppercase tracking-wider font-medium opacity-70">
                      {labels[s.research_source] || s.research_source}
                    </p>
                    <p className="text-2xl font-bold tracking-tight mt-0.5">{s.total.toLocaleString()}</p>
                    <p className="text-[10px] opacity-60 mt-0.5">
                      {s.category_count} categories · {s.jurisdiction_count} jurisdictions
                    </p>
                    {s.latest && (
                      <p className="text-[10px] opacity-40 mt-0.5">Last: {fmtDate(s.latest)}</p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Official API category breakdown */}
          {data.api_by_category.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                Official API Data by Category
              </h2>
              <div className="border border-zinc-800 rounded-lg p-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {data.api_by_category.map((c) => (
                    <div key={c.category} className="flex items-center justify-between px-2 py-1.5 rounded bg-zinc-900/50">
                      <span className="text-[11px] text-zinc-300">{getCategoryLabel(c.category)}</span>
                      <span className="text-[11px] font-mono font-bold text-emerald-400">{c.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Recent official API entries */}
          {data.recent_api.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                Recent Official API Entries ({data.recent_api.length})
              </h2>
              <div className="border border-zinc-800 rounded-lg overflow-hidden">
                <div className="max-h-[50vh] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                      <tr>
                        <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Title</th>
                        <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Category</th>
                        <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Location</th>
                        <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Source</th>
                        <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Updated</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800">
                      {data.recent_api.map((r) => (
                        <Fragment key={r.id}>
                          <tr className="hover:bg-zinc-800/30 cursor-pointer" onClick={() => setExpandedApiRow(expandedApiRow === r.id ? null : r.id)}>
                            <td className="py-2 px-3 text-zinc-200 max-w-xs">
                              <p className="truncate text-[11px]">
                                <span className="text-zinc-600 mr-1">{expandedApiRow === r.id ? '▾' : '▸'}</span>
                                {r.title}
                              </p>
                            </td>
                            <td className="py-2 px-3">
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 whitespace-nowrap">
                                {getShortLabel(r.category)}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-zinc-400 text-[11px] whitespace-nowrap">
                              {r.city ? `${r.city}, ${r.state}` : r.state} · {r.jurisdiction_level}
                            </td>
                            <td className="py-2 px-3 text-[11px]">
                              {r.source_url ? (
                                <a href={r.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                                  className="text-emerald-500/70 hover:text-emerald-400 underline">{r.source_name || 'Link'}</a>
                              ) : (
                                <span className="text-zinc-600">{r.source_name || '—'}</span>
                              )}
                            </td>
                            <td className="py-2 px-3 text-zinc-500 text-[11px] whitespace-nowrap">
                              {r.updated_at ? fmtDate(r.updated_at) : r.created_at ? fmtDate(r.created_at) : '—'}
                            </td>
                          </tr>
                          {expandedApiRow === r.id && (
                            <tr className="bg-zinc-900/40">
                              <td colSpan={5} className="px-4 py-3">
                                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[11px]">
                                  {r.description && (
                                    <div className="col-span-2">
                                      <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Description</p>
                                      <p className="text-zinc-300 leading-relaxed">{r.description}</p>
                                    </div>
                                  )}
                                  {r.current_value && (
                                    <div>
                                      <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Current Value</p>
                                      <p className="text-zinc-300">{r.current_value}</p>
                                    </div>
                                  )}
                                  <div>
                                    <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Category</p>
                                    <p className="text-zinc-300">{getCategoryLabel(r.category)}</p>
                                  </div>
                                  <div>
                                    <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Jurisdiction</p>
                                    <p className="text-zinc-300">{r.jurisdiction_name || r.jurisdiction_level} · {r.city ? `${r.city}, ${r.state}` : r.state}</p>
                                  </div>
                                  {r.effective_date && (
                                    <div>
                                      <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Effective Date</p>
                                      <p className="text-zinc-300">{r.effective_date}</p>
                                    </div>
                                  )}
                                  <div>
                                    <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Added</p>
                                    <p className="text-zinc-300">{r.created_at ? fmtDate(r.created_at) : '—'}</p>
                                  </div>
                                  {r.last_verified_at && (
                                    <div>
                                      <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Last Verified</p>
                                      <p className="text-zinc-300">{fmtDate(r.last_verified_at)}</p>
                                    </div>
                                  )}
                                  {r.source_url && (
                                    <div className="col-span-2">
                                      <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Source URL</p>
                                      <a href={r.source_url} target="_blank" rel="noreferrer"
                                        className="text-emerald-500/70 hover:text-emerald-400 underline break-all">{r.source_url}</a>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {data.source_counts.length === 0 && data.recent_api.length === 0 && (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No research source data yet. Use the "Fed Sources" button on a jurisdiction to fetch from government APIs.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
