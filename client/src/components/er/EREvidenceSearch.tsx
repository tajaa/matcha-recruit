import { useState } from 'react'
import { api } from '../../api/client'
import { Badge } from '../ui'
import type { EvidenceSearchResponse, EvidenceSearchResult } from '../../types/er'
import { documentTypeLabel } from '../../types/er'

type Props = { caseId: string }

export function EREvidenceSearch({ caseId }: Props) {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [data, setData] = useState<EvidenceSearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function search() {
    const q = query.trim()
    if (!q) return
    setLoading(true)
    setError('')
    try {
      const res = await api.post<EvidenceSearchResponse>(`/er/cases/${caseId}/search`, { query: q, top_k: topK })
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  function similarityColor(s: number) {
    if (s >= 0.7) return 'bg-emerald-500/60'
    if (s >= 0.4) return 'bg-amber-500/60'
    return 'bg-red-500/60'
  }

  return (
    <div className="space-y-4">
      {/* Search input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') search() }}
          placeholder="Search evidence..."
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
        />
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-sm text-zinc-300 focus:outline-none focus:border-zinc-500"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
        </select>
        <button
          type="button"
          onClick={search}
          disabled={loading || !query.trim()}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* Results */}
      {data && (
        <>
          <p className="text-xs text-zinc-500">
            {data.results.length} result{data.results.length !== 1 ? 's' : ''} for &lsquo;{data.query}&rsquo;
            {data.total_chunks > 0 && <span className="text-zinc-600"> &middot; {data.total_chunks} chunks indexed</span>}
          </p>

          {data.results.length === 0 && (
            <p className="text-sm text-zinc-400 text-center py-6">No matching evidence found.</p>
          )}

          {data.results.map((r: EvidenceSearchResult) => (
            <div key={r.chunk_id} className="border border-zinc-800 rounded-lg p-4 space-y-2">
              <p className="text-sm text-zinc-200 leading-relaxed">{r.content}</p>

              <div className="flex flex-wrap items-center gap-2">
                {r.speaker && <Badge variant="neutral">{r.speaker}</Badge>}
                <Badge variant="neutral">{documentTypeLabel[r.document_type] ?? r.document_type}</Badge>
                <span className="text-[11px] text-zinc-500 font-mono">{r.source_file}</span>
                {r.page_number != null && (
                  <span className="text-[11px] text-zinc-600">p.{r.page_number}</span>
                )}
                {r.line_range && (
                  <span className="text-[11px] text-zinc-600">lines {r.line_range}</span>
                )}
              </div>

              {/* Similarity bar */}
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${similarityColor(r.similarity)}`}
                    style={{ width: `${Math.round(r.similarity * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] font-mono text-zinc-500">{Math.round(r.similarity * 100)}%</span>
              </div>
            </div>
          ))}
        </>
      )}

      {/* Empty state before first search */}
      {!data && !loading && (
        <p className="text-sm text-zinc-500 text-center py-6">
          Search across all uploaded documents for specific evidence, quotes, or topics.
        </p>
      )}
    </div>
  )
}
