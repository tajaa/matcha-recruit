import { useState } from 'react'
import { analyzeProtocol, type ProtocolAnalysisResult, type ProtocolAnalysisItem } from '../../api/compliance'

type Props = {
  locationId?: string | null
}

function StatusBadge({ status }: { status: string }) {
  const styles = {
    covered: 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40',
    gap: 'bg-red-900/40 text-red-400 border-red-700/40',
    partial: 'bg-amber-900/40 text-amber-400 border-amber-700/40',
  }
  const labels = { covered: 'Covered', gap: 'Gap', partial: 'Partial' }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${styles[status as keyof typeof styles] || styles.gap}`}>
      {labels[status as keyof typeof labels] || status}
    </span>
  )
}

function ResultSection({ title, items, color, defaultOpen }: {
  title: string
  items: ProtocolAnalysisItem[]
  color: string
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  if (items.length === 0) return null

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className={`w-full flex items-center justify-between px-3 py-2 text-sm font-medium ${color} hover:bg-zinc-800/50 transition-colors`}
      >
        <span>{title} ({items.length})</span>
        <span className="text-zinc-500">{open ? '-' : '+'}</span>
      </button>
      {open && (
        <div className="divide-y divide-zinc-800/50">
          {items.map((item, i) => (
            <div key={i} className="px-3 py-2">
              <div className="flex items-center gap-2">
                <StatusBadge status={item.status} />
                <span className="text-sm text-zinc-200">{item.title}</span>
              </div>
              {item.evidence && (
                <p className="mt-1 text-xs text-zinc-400 leading-5 pl-[52px]">{item.evidence}</p>
              )}
              {item.guidance && (
                <p className="mt-1 text-xs text-amber-400/80 leading-5 pl-[52px]">{item.guidance}</p>
              )}
              {item.missing && (
                <p className="mt-1 text-xs text-red-400/80 leading-5 pl-[52px]">Missing: {item.missing}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ProtocolAnalysis({ locationId }: Props) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ProtocolAnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleAnalyze() {
    if (!text.trim() || loading) return
    setLoading(true)
    setResult(null)
    setError(null)

    try {
      const data = await analyzeProtocol(text.trim(), locationId ?? undefined)
      setResult(data)
    } catch (e: any) {
      setError(e.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setText('')
    setResult(null)
    setError(null)
  }

  return (
    <div>
      <div className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste your study protocol or procedure document..."
          rows={6}
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700 resize-y"
          disabled={loading}
        />
        <div className="flex items-center gap-2">
          <button
            onClick={handleAnalyze}
            disabled={!text.trim() || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Analyzing...
              </span>
            ) : (
              'Analyze Protocol'
            )}
          </button>
          {result && (
            <button onClick={handleClear} className="text-xs text-zinc-500 hover:text-zinc-300">
              Clear
            </button>
          )}
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
            <span className="text-[10px] text-indigo-400 uppercase tracking-wide font-medium">Analysis Summary</span>
            <p className="mt-1 text-sm text-zinc-200 leading-6">{result.summary}</p>
            <p className="mt-2 text-[11px] text-zinc-500">{result.requirements_analyzed} requirements analyzed</p>
          </div>

          <ResultSection
            title="Gaps"
            items={result.gaps}
            color="text-red-400"
            defaultOpen={true}
          />
          <ResultSection
            title="Partial Coverage"
            items={result.partial}
            color="text-amber-400"
            defaultOpen={true}
          />
          <ResultSection
            title="Covered"
            items={result.covered}
            color="text-emerald-400"
            defaultOpen={false}
          />
        </div>
      )}
    </div>
  )
}
