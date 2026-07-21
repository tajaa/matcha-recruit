import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronRight, AlertTriangle, ExternalLink } from 'lucide-react'
import { safeUrl } from '../../utils/safeUrl'

/** A grounded-answer citation. Shape matches the server corpus record emitted by
 *  `services/hr_pilot_corpus.py` (HR Pilot threads today, employee Ask HR next) —
 *  the server has already dropped any id that didn't resolve, so everything here
 *  is a real record. */
export interface Citation {
  cid: string
  ref: string
  summary?: string
  when?: string
  source?: string
  source_label?: string
  source_url?: string | null
}

/** Rewrite raw `[cid]` markers into reader-friendly `[n]` markers numbered by
 *  first use, and return the citations in that same order.
 *
 *  The model cites by corpus id because ids are what the server-side gate can
 *  verify; a supervisor should not have to read
 *  `[floor:state-california-meal-rest-breaks]` mid-sentence. Numbering happens
 *  here, at render time, so the stored message keeps the verifiable ids.
 *
 *  Citations the answer never actually cites inline are still returned (appended
 *  after the numbered ones, unnumbered) rather than hidden — they were grounded
 *  material for the answer even if no marker survived. */
export function numberCitations(
  content: string,
  citations: Citation[] | undefined,
): { text: string; ordered: (Citation & { n?: number })[] } {
  if (!content || !citations?.length) return { text: content ?? '', ordered: [] }

  const byCid = new Map(citations.map(c => [c.cid, c]))
  const order: string[] = []
  const text = content.replace(/\[([a-z_]+(?::[^\]\s]+)?)\]/g, (whole, cid: string) => {
    if (!byCid.has(cid)) return whole
    let n = order.indexOf(cid)
    if (n === -1) { order.push(cid); n = order.length - 1 }
    return `[${n + 1}]`
  })

  const ordered: (Citation & { n?: number })[] = order.map((cid, i) => ({ ...byCid.get(cid)!, n: i + 1 }))
  for (const c of citations) {
    if (!order.includes(c.cid)) ordered.push(c)
  }
  return { text, ordered }
}

export default function CitationSources({
  citations,
  dropped,
  lightMode,
}: {
  citations: (Citation & { n?: number })[]
  dropped?: string[]
  lightMode?: boolean
}) {
  const [open, setOpen] = useState(false)
  if (!citations?.length && !dropped?.length) return null

  const lm = lightMode
  const divider = lm ? 'border-zinc-200' : 'border-zinc-800'
  const metaText = lm ? 'text-zinc-400' : 'text-zinc-500'
  const chip = lm ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-800 text-zinc-400'

  return (
    <div className={`mt-2 pt-2 border-t ${divider}`}>
      {citations.length > 0 && (
        <>
          <button
            onClick={() => setOpen(o => !o)}
            className={`flex items-center gap-1 text-[10px] ${metaText} uppercase tracking-wide hover:opacity-80`}
          >
            {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            <BookOpen size={10} />
            Sources ({citations.length})
          </button>
          {open && (
            <ol className="mt-1.5 space-y-1.5">
              {citations.map(c => {
                // The corpus `source_url` is server-side but model-adjacent, and
                // MessageBubble gates the same field — a `javascript:` href here
                // would run in the reader's session.
                const href = safeUrl(c.source_url)
                return (
                <li key={c.cid} className={`flex gap-1.5 text-[11px] ${lm ? 'text-zinc-600' : 'text-zinc-400'}`}>
                  <span className={`shrink-0 px-1 rounded ${chip} font-medium`}>
                    {c.n ?? '·'}
                  </span>
                  <span className="min-w-0">
                    <span className={lm ? 'text-zinc-800' : 'text-zinc-200'}>{c.ref}</span>
                    {c.source_label && (
                      <span className={`ml-1 ${metaText}`}>· {c.source_label}</span>
                    )}
                    {href && (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-1 inline-flex items-center text-emerald-500 hover:text-emerald-400"
                      >
                        <ExternalLink size={9} />
                      </a>
                    )}
                    {c.summary && <span className="block opacity-70">{c.summary}</span>}
                  </span>
                </li>
                )
              })}
            </ol>
          )}
        </>
      )}
      {dropped && dropped.length > 0 && (
        // Surfaced, not swallowed: an answer leaning on sources that don't exist
        // should be legible as such, even though the ids themselves are gone.
        <div className={`mt-1.5 flex items-start gap-1 text-[10px] ${lm ? 'text-amber-600' : 'text-amber-500/80'}`}>
          <AlertTriangle size={10} className="shrink-0 mt-px" />
          <span>
            {dropped.length} unverifiable citation{dropped.length !== 1 ? 's' : ''} removed — treat
            any claim without a source above as unconfirmed.
          </span>
        </div>
      )}
    </div>
  )
}
