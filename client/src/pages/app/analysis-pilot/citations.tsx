import { useMemo } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cidFallbackLabel, linkifyCids, type CidInfo } from './shared'

export function CidChip({ label, summary }: { label: string; summary?: string }) {
  return (
    <span title={summary}
      className="mx-0.5 inline-flex items-center rounded-sm border border-emerald-500/25 bg-emerald-500/[0.07] px-1.5 py-px align-baseline font-mono text-[10px] text-emerald-300/90 no-underline">
      {label}
    </span>
  )
}

/** Render one or more cids as chips (used by evidence map + reasoning steps). */
export function CidChips({ cids, idx }: { cids: string[]; idx: Map<string, CidInfo> }) {
  if (!cids.length) return null
  return (
    <span className="inline-flex flex-wrap gap-0.5 align-middle">
      {cids.map((cid) => (
        <CidChip key={cid} label={idx.get(cid)?.ref || cidFallbackLabel(cid)} summary={idx.get(cid)?.summary} />
      ))}
    </span>
  )
}

/** Assistant prose: markdown + inline citation chips. */
export function CitedMarkdown({ text, idx }: { text: string; idx: Map<string, CidInfo> }) {
  const processed = useMemo(() => linkifyCids(text, idx), [text, idx])
  return (
    <div className="prose prose-sm prose-invert prose-zinc max-w-none prose-p:my-1.5 prose-headings:text-zinc-100 prose-headings:text-sm prose-strong:text-zinc-100 prose-li:my-0.5">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (typeof href === 'string' && href.startsWith('#cid:')) {
              const cid = href.slice(5)
              return <CidChip label={idx.get(cid)?.ref || cidFallbackLabel(cid)} summary={idx.get(cid)?.summary} />
            }
            return <a href={href} target="_blank" rel="noreferrer" className="text-emerald-400 underline">{children}</a>
          },
        }}
      >
        {processed}
      </Markdown>
    </div>
  )
}
