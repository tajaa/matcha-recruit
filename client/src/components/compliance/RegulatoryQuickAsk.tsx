import { useState, useRef } from 'react'
import { askRegulatoryQuestion, type RegulatoryQASource } from '../../api/compliance'

type Props = {
  locationId?: string | null
  /** Open a cited requirement in the Requirements tab (by catalog id). The title
   *  is the fallback target when that row isn't in the location's list. */
  onOpenSource?: (requirementId: string, title?: string | null) => void
}

export function RegulatoryQuickAsk({ locationId, onOpenSource }: Props) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState<string | null>(null)
  const [sources, setSources] = useState<RegulatoryQASource[]>([])
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleAsk() {
    const q = query.trim()
    if (!q || loading) return

    setLoading(true)
    setAnswer(null)
    setSources([])
    setError(null)

    try {
      const result = await askRegulatoryQuestion(q, locationId ?? undefined)
      setAnswer(result.answer)
      setSources(result.sources)
    } catch (e: any) {
      setError(e.message || 'Failed to get answer')
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setQuery('')
    setAnswer(null)
    setSources([])
    setError(null)
    inputRef.current?.focus()
  }

  return (
    <div className="mb-4">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
          placeholder="Ask a regulatory question..."
          className="w-full bg-zinc-900/40 border border-white/[0.06] rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700"
          disabled={loading}
        />
        {loading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-400">{error}</p>
      )}

      {answer && (
        <div className="mt-3 bg-zinc-900/40 border border-white/[0.06] rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-indigo-400 uppercase tracking-wide font-medium">Regulatory Answer</span>
            <button
              onClick={handleClear}
              className="text-[10px] text-zinc-500 hover:text-zinc-300"
            >
              Clear
            </button>
          </div>
          <p className="text-sm text-zinc-200 leading-6 whitespace-pre-wrap">{answer}</p>

          {sources.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/[0.06]">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Sources ({sources.length})</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {sources.map((s, i) => {
                  const canOpen = !!onOpenSource && !!s.requirement_id
                  // The chip opens the requirement in THEIR Requirements tab —
                  // not the external statute site (that URL lives on the row).
                  return canOpen ? (
                    <button
                      key={i}
                      type="button"
                      onClick={() => onOpenSource!(s.requirement_id, s.title)}
                      className="inline-flex items-center gap-1 text-[11px] bg-white/[0.06] hover:bg-white/[0.10] text-zinc-400 hover:text-zinc-200 px-2 py-0.5 rounded transition-colors"
                      title="Open this requirement in your Requirements tab"
                    >
                      <span className="text-indigo-400">{s.jurisdiction_name}</span>
                      <span className="text-zinc-600">|</span>
                      <span>{s.category}</span>
                      <span className="text-zinc-600">→</span>
                    </button>
                  ) : (
                    <span key={i} className="inline-flex items-center gap-1 text-[11px] bg-white/[0.06] text-zinc-400 px-2 py-0.5 rounded">
                      <span className="text-indigo-400">{s.jurisdiction_name}</span>
                      <span className="text-zinc-600">|</span>
                      <span>{s.category}</span>
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
