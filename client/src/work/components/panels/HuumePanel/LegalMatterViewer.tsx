import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { getMatter, type Matter } from '../../../../api/legal-defense/legalDefense'
import { pickLatestMemo, tokenizeCids } from './legalMemo'

interface LegalMatterViewerProps {
  matterId: string
  lightMode?: boolean
  /** True while Huume is streaming a turn. `huume_legal` only ever carries
   * `{matter_id, title}` — a new `ask_legal_pilot` turn on the SAME matter
   * doesn't change either, so matterId alone can't signal "there's a new
   * memo". Refetch on each true→false edge instead of only on mount. */
  streaming?: boolean
}

function MemoText({ text }: { text: string }) {
  return (
    <p className="max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed">
      {tokenizeCids(text).map((part, i) =>
        typeof part === 'string'
          ? <span key={i}>{part}</span>
          : (
            <span
              key={i}
              title={part.id}
              className="mx-0.5 inline-flex items-center rounded border border-zinc-700 bg-zinc-800/60 px-1 py-0.5 align-middle text-[10px] capitalize text-zinc-300"
            >
              {part.type.replace(/_/g, ' ')}
            </span>
          ))}
    </p>
  )
}

/** Renders the legal matter's memo — the newest analysis turn (same
 * selection rule as services/pilots/legal_defense/matters.py:latest_memo) —
 * plus its evidence map and open questions. The memo body is plain text with
 * inline cid tokens, so it's rendered with a lightweight non-clickable pill
 * tokenizer rather than markdown (there is no clickable RecordViewer here in
 * v1 — that needs a separate getEvidence() fetch to label the chips). */
export default function LegalMatterViewer({ matterId, lightMode, streaming }: LegalMatterViewerProps) {
  const [matter, setMatter] = useState<Matter | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setMatter(await getMatter(matterId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the legal matter')
    } finally {
      setLoading(false)
    }
  }, [matterId])

  useEffect(() => { void load() }, [load])

  const wasStreaming = useRef(streaming)
  useEffect(() => {
    if (wasStreaming.current && !streaming) void load()
    wasStreaming.current = streaming
  }, [streaming, load])

  const muted = lightMode ? 'text-zinc-500' : 'text-zinc-500'
  const border = lightMode ? 'border-zinc-200' : 'border-zinc-800'

  if (loading) {
    return (
      <div className="flex w-full flex-1 items-center justify-center">
        <Loader2 size={18} className={`animate-spin ${muted}`} />
      </div>
    )
  }

  if (error || !matter) {
    return (
      <div className="flex w-full flex-1 items-center justify-center px-4 text-center">
        <p className={`text-sm ${muted}`}>{error ?? 'Failed to load the legal matter'}</p>
      </div>
    )
  }

  const memo = pickLatestMemo(matter.messages ?? [])

  return (
    <div className="flex w-full flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div>
        <h3 className="text-sm font-semibold">{matter.title}</h3>
        <span className={`text-[11px] capitalize ${muted}`}>{matter.matter_type.replace(/_/g, ' ')} · {matter.status}</span>
      </div>

      {!memo && <p className={`text-sm ${muted}`}>No analysis yet — ask Huume to work this matter in chat.</p>}

      {memo && (
        <>
          <MemoText text={memo.content} />

          {(memo.metadata?.evidence_map?.length ?? 0) > 0 && (
            <div className={`rounded border p-2.5 ${lightMode ? 'border-emerald-300 bg-emerald-50' : 'border-emerald-800 bg-emerald-950/20'}`}>
              <div className="mb-1 text-[10px] uppercase tracking-wide opacity-70">Evidence map</div>
              <ul className="space-y-1.5">
                {memo.metadata!.evidence_map!.map((item, i) => (
                  <li key={i} className="text-xs"><MemoText text={item.point} /></li>
                ))}
              </ul>
            </div>
          )}

          {(memo.metadata?.open_questions?.length ?? 0) > 0 && (
            <div className={`rounded border p-2.5 ${lightMode ? 'border-amber-300 bg-amber-50' : 'border-amber-800 bg-amber-950/20'}`}>
              <div className="mb-1 text-[10px] uppercase tracking-wide opacity-70">Open questions</div>
              <ul className="list-disc space-y-1 pl-4 text-xs">
                {memo.metadata!.open_questions!.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </div>
          )}
        </>
      )}

      <div className={`mt-1 border-t pt-2 ${border}`}>
        <Link to="/app/legal-pilot" className="text-xs font-medium text-orange-500 hover:text-orange-400">
          Open Legal Pilot →
        </Link>
      </div>
    </div>
  )
}
