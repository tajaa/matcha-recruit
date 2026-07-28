import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CheckCircle2, Loader2 } from 'lucide-react'
import {
  getPilotHandbook, type AssembledSection,
} from '../../../../api/handbook-pilot/handbookPilot'
import type { HuumeHandbook } from '../../../types'

interface HandbookDraftsViewerProps {
  sessionId: string
  pendingDrafts: HuumeHandbook['pending_drafts']
  lightMode?: boolean
}

// Same rule as pages/app/handbook-pilot/HandbookViewer.tsx:38-40 — placeholder
// tokens like [HR_CONTACT_EMAIL] must survive as literal text; wrap them in
// inline-code so prose styling makes them pop, without touching markdown
// link syntax [text](url).
function highlightPlaceholders(md: string): string {
  return (md || '').replace(/\[([A-Z0-9_]{2,})\](?!\()/g, '`[$1]`')
}

/** Renders the handbook drafts a Huume thread has pending — reuses the
 * assembled-handbook read path (GET /handbook-pilot/pilot/sessions/{id}/handbook),
 * which serves markdown with corpus citation tags already stripped, unlike the
 * raw session-drafts endpoint. */
export default function HandbookDraftsViewer({ sessionId, pendingDrafts, lightMode }: HandbookDraftsViewerProps) {
  const [sections, setSections] = useState<AssembledSection[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const hb = await getPilotHandbook(sessionId)
      setSections([...hb.sections, ...hb.policies])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load handbook drafts')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { void load() }, [load])

  const muted = lightMode ? 'text-zinc-500' : 'text-zinc-500'
  const prose = lightMode
    ? 'prose prose-sm prose-zinc max-w-none'
    : 'prose prose-sm prose-invert prose-zinc max-w-none'

  if (loading) {
    return (
      <div className="flex w-full flex-1 items-center justify-center">
        <Loader2 size={18} className={`animate-spin ${muted}`} />
      </div>
    )
  }

  if (error || !sections) {
    return (
      <div className="flex w-full flex-1 items-center justify-center px-4 text-center">
        <p className={`text-sm ${muted}`}>{error ?? 'Failed to load handbook drafts'}</p>
      </div>
    )
  }

  const wanted = new Set(pendingDrafts.map((d) => d.draft_id))
  let items = sections.filter((s) => wanted.has(s.id))
  if (items.length === 0) items = sections.filter((s) => s.status === 'pending')

  return (
    <div className="flex w-full flex-1 flex-col gap-4 overflow-y-auto p-4">
      {items.map((s) => (
        <div key={s.id} className={`border-b pb-3 last:border-b-0 ${lightMode ? 'border-zinc-200' : 'border-zinc-800'}`}>
          <div className="mb-1.5 flex items-center gap-2">
            <h3 className="text-sm font-semibold">{s.title}</h3>
            <span className={`rounded border px-1.5 py-0.5 text-[10px] capitalize ${lightMode ? 'border-zinc-300 text-zinc-600' : 'border-zinc-700 text-zinc-400'}`}>
              {s.kind === 'handbook_section' ? 'Section' : 'Policy'}
            </span>
            {s.grounded && (
              <span className="flex items-center gap-1 rounded border border-emerald-800 bg-emerald-950/30 px-1.5 py-0.5 text-[10px] text-emerald-400">
                <CheckCircle2 size={10} /> Grounded
              </span>
            )}
          </div>
          <div className={prose}>
            <Markdown remarkPlugins={[remarkGfm]}>{highlightPlaceholders(s.content)}</Markdown>
          </div>
          {s.citations.length > 0 && (
            <p className={`mt-1.5 text-[10px] ${muted}`}>
              {s.citations.length} citation{s.citations.length !== 1 ? 's' : ''} · {s.law_citation_count} to law
            </p>
          )}
        </div>
      ))}
      <Link to="/app/handbook-pilot" className="text-xs font-medium text-orange-500 hover:text-orange-400">
        Open Handbook Pilot →
      </Link>
    </div>
  )
}
