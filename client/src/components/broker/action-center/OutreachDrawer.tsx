import { useEffect, useState } from 'react'
import { X, RefreshCw, Sparkles, ExternalLink, Loader2 } from 'lucide-react'
import { fetchActionCenterOutreach } from '../../../api/broker'
import type { OutreachResponse, OutreachTone } from '../../../types/broker'

const TONE_TONE: Record<OutreachTone, { bg: string; text: string; label: string }> = {
  celebratory: { bg: 'bg-emerald-500/10 border-emerald-500/20', text: 'text-emerald-400', label: 'Celebrate' },
  advisory:    { bg: 'bg-amber-500/10 border-amber-500/20',     text: 'text-amber-400',   label: 'Advise' },
  urgent:      { bg: 'bg-red-500/10 border-red-500/20',         text: 'text-red-400',     label: 'Urgent' },
}

// Internal resource slugs map to human labels. The backend only ever returns a
// slug from its allow-list (never a model-invented URL).
const RESOURCE_LABELS: Record<string, string> = {
  'safety-guide': 'Safety program guide',
  'eap-overview': 'EAP overview',
  'renewal-prep': 'Renewal prep checklist',
  'ergonomics-kit': 'Ergonomics kit',
  'return-to-work': 'Return-to-work toolkit',
}

interface OutreachDrawerProps {
  companyId: string
  companyName: string
  onClose: () => void
}

export function OutreachDrawer({ companyId, companyName, onClose }: OutreachDrawerProps) {
  const [data, setData] = useState<OutreachResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  function load(refresh = false) {
    setLoading(true)
    setError(null)
    fetchActionCenterOutreach(companyId, refresh)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load outreach ideas'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId])

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative w-full max-w-md h-full bg-zinc-950 border-l border-white/10 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-white/10 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 text-zinc-100">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <h2 className="text-sm font-semibold">Outreach ideas</h2>
            </div>
            <p className="text-[11px] text-zinc-500 mt-0.5">{companyName}</p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => load(true)}
              title="Regenerate"
              className="p-1.5 text-zinc-500 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button type="button" onClick={onClose} className="p-1.5 text-zinc-500 hover:text-zinc-200 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          <p className="text-[10px] text-zinc-600 leading-relaxed">
            Consultative talking points generated from this client's aggregate safety trends — no individual incident
            details. Use them to open a proactive conversation, not as a deliverable.
          </p>

          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-5 h-5 text-zinc-600 animate-spin" />
            </div>
          )}

          {error && !loading && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 text-xs text-red-400">{error}</div>
          )}

          {!loading && !error && data && data.prompts.length === 0 && (
            <p className="text-sm text-zinc-500 py-8 text-center">No outreach ideas right now.</p>
          )}

          {!loading && !error && data?.prompts.map((p, i) => {
            const tone = TONE_TONE[p.tone] ?? TONE_TONE.advisory
            return (
              <div key={i} className="bg-zinc-900 border border-white/10 rounded-xl p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-[13px] font-medium text-zinc-100 leading-snug">{p.title}</h3>
                  <span className={`shrink-0 px-2 py-0.5 text-[9px] uppercase tracking-widest font-bold rounded border ${tone.bg} ${tone.text}`}>
                    {tone.label}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 leading-relaxed">{p.rationale}</p>
                <p className="text-[12px] text-zinc-300 leading-relaxed">{p.suggested_action}</p>
                {p.resource_link && (
                  <div className="inline-flex items-center gap-1.5 text-[11px] text-emerald-400">
                    <ExternalLink className="w-3 h-3" />
                    {RESOURCE_LABELS[p.resource_link] ?? p.resource_link}
                  </div>
                )}
              </div>
            )
          })}

          {!loading && data?.cached && (
            <p className="text-[10px] text-zinc-700 text-center pt-2">
              Cached — use ↻ to regenerate from the latest trends.
            </p>
          )}
        </div>
      </aside>
    </div>
  )
}

export default OutreachDrawer
