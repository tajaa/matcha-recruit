import { useState } from 'react'
import Markdown from 'react-markdown'
import { draftPolicy, type PolicyDraftResult } from '../../api/compliance'

type Props = {
  locationId?: string | null
}

export function PolicyDrafter({ locationId }: Props) {
  const [topic, setTopic] = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [industryContext, setIndustryContext] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PolicyDraftResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  async function handleDraft() {
    if (!topic.trim() || !jurisdiction.trim() || loading) return
    setLoading(true)
    setResult(null)
    setError(null)

    try {
      const data = await draftPolicy(
        topic.trim(),
        jurisdiction.trim(),
        locationId ?? undefined,
        industryContext.trim() || undefined,
      )
      setResult(data)
    } catch (e: any) {
      setError(e.message || 'Failed to draft policy')
    } finally {
      setLoading(false)
    }
  }

  function handleCopy() {
    if (!result) return
    navigator.clipboard.writeText(result.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleClear() {
    setTopic('')
    setJurisdiction('')
    setIndustryContext('')
    setResult(null)
    setError(null)
  }

  return (
    <div>
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic (e.g., Meal and Rest Breaks, HIPAA Privacy)"
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700"
            disabled={loading}
          />
          <input
            type="text"
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDraft()}
            placeholder="Jurisdiction (e.g., California, Federal)"
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700"
            disabled={loading}
          />
        </div>
        <input
          type="text"
          value={industryContext}
          onChange={(e) => setIndustryContext(e.target.value)}
          placeholder="Industry context (optional, e.g., oncology clinic, nursing facility)"
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700"
          disabled={loading}
        />
        <div className="flex items-center gap-2">
          <button
            onClick={handleDraft}
            disabled={!topic.trim() || !jurisdiction.trim() || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Drafting...
              </span>
            ) : (
              'Draft Policy'
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
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-zinc-100">{result.title}</h3>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{result.category}</span>
                {result.applicable_jurisdictions.map((j, i) => (
                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-indigo-400 border border-zinc-700">
                    {j}
                  </span>
                ))}
              </div>
            </div>
            <button
              onClick={handleCopy}
              className="text-xs px-3 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          {/* Policy content */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-5 prose prose-invert prose-sm max-w-none">
            <Markdown>{result.content}</Markdown>
          </div>

          {/* Citations */}
          {result.citations.length > 0 && (
            <div className="border border-zinc-800 rounded-lg p-3">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Regulatory Citations ({result.citations.length})</span>
              <div className="mt-2 space-y-1">
                {result.citations.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="text-zinc-400">{c.title}</span>
                    {c.source_url && (
                      <a
                        href={c.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-500 hover:text-indigo-400 shrink-0"
                      >
                        source
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
