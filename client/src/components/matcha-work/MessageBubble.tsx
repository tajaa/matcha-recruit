import React, { useMemo } from 'react'
import { FileText, Package, PlusCircle } from 'lucide-react'
import Markdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import type { MWMessage } from '../../types/matcha-work'
import ComplianceReasoningPanel from './ComplianceReasoningPanel'

function extractPenalties(reasoning: MWMessage['metadata']): { category: string; summary: string; agency: string }[] {
  if (!reasoning?.compliance_reasoning) return []
  const refCats = new Set(reasoning.referenced_categories ?? [])
  const refLocs = new Set(reasoning.referenced_locations ?? [])
  // Only show enforcement risk when the AI actually referenced compliance categories
  if (refCats.size === 0) return []
  const seen = new Set<string>()
  const results: { category: string; summary: string; agency: string }[] = []
  for (const loc of reasoning.compliance_reasoning) {
    // Skip locations not referenced in the answer
    if (refLocs.size > 0 && !refLocs.has(loc.location_label) &&
        !Array.from(refLocs).some(r => loc.location_label.includes(r) || r.includes(loc.location_label.split('(')[0]?.trim() ?? ''))) continue
    for (const cat of loc.categories) {
      if (seen.has(cat.category)) continue
      if (!refCats.has(cat.category)) continue
      const gov = cat.all_levels.find(l => l.is_governing)
      if (gov?.penalty_summary) {
        seen.add(cat.category)
        results.push({
          category: cat.category.replace(/_/g, ' '),
          summary: gov.penalty_summary,
          agency: gov.enforcing_agency || '',
        })
      }
    }
  }
  return results
}

const MessageBubble = React.memo(function MessageBubble({ message: m, lightMode, isProjectThread, onAddToProject }: {
  message: MWMessage
  lightMode?: boolean
  isProjectThread?: boolean
  onAddToProject?: (messageId: string, content: string) => void
}) {
  const markdownContent = useMemo(() => (
    <Markdown rehypePlugins={[rehypeRaw]}>{m.content}</Markdown>
  ), [m.content])
  const penalties = useMemo(() => extractPenalties(m.metadata), [m.metadata])

  const lm = isProjectThread ? false : lightMode
  const divider  = isProjectThread ? 'border-[#333]' : lm ? 'border-zinc-200' : 'border-zinc-800'
  const metaText = isProjectThread ? 'text-[#6a737d]' : lm ? 'text-zinc-400' : 'text-zinc-500'

  return (
    <div className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] sm:max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
          m.role === 'user'
            ? isProjectThread
              ? 'bg-[#2a2d2e] text-[#d4d4d4] whitespace-pre-wrap'
              : lm
                ? 'bg-zinc-200 text-zinc-900 whitespace-pre-wrap'
                : 'bg-zinc-700 text-white whitespace-pre-wrap'
            : isProjectThread
              ? 'bg-[#252526] text-[#d4d4d4] border border-[#333] prose prose-sm prose-invert prose-zinc max-w-none overflow-x-auto'
              : lm
                ? 'bg-zinc-50 text-zinc-800 border border-zinc-200 prose prose-sm prose-zinc max-w-none overflow-x-auto'
              : 'bg-zinc-800/60 text-zinc-200 border border-zinc-700/50 prose prose-sm prose-invert prose-zinc max-w-none overflow-x-auto'
        }`}
      >
        {m.role === 'user' && (m.content.startsWith('[Resume uploaded:') || m.content.startsWith('[Resume batch:') || m.content.startsWith('[Inventory batch:')) ? (
          (() => {
            if (m.content.startsWith('[Inventory batch:')) {
              const countMatch = m.content.match(/\[Inventory batch: (\d+) files?\]/)
              const count = countMatch?.[1] ?? '?'
              return (
                <div className={`flex items-center gap-2 ${lm ? 'text-amber-700' : 'text-amber-300'}`}>
                  <Package size={16} className="shrink-0" />
                  <span>Uploaded <strong>{count} invoice{count !== '1' ? 's' : ''}</strong></span>
                </div>
              )
            }
            if (m.content.startsWith('[Resume batch:')) {
              const countMatch = m.content.match(/\[Resume batch: (\d+) files?\]/)
              const count = countMatch?.[1] ?? '?'
              return (
                <div className={`flex items-center gap-2 ${lm ? 'text-emerald-700' : 'text-emerald-300'}`}>
                  <FileText size={16} className="shrink-0" />
                  <span>Uploaded <strong>{count} resumes</strong></span>
                </div>
              )
            }
            const filename = m.content.match(/\[Resume uploaded: (.+?)\]/)?.[1] ?? 'resume'
            return (
              <div className={`flex items-center gap-2 ${lm ? 'text-emerald-700' : 'text-emerald-300'}`}>
                <FileText size={16} className="shrink-0" />
                <span>Uploaded resume: <strong>{filename}</strong></span>
              </div>
            )
          })()
        ) : m.role === 'assistant' ? (
          <>
            {markdownContent}
            {isProjectThread && onAddToProject && (
              <button
                onClick={() => onAddToProject(m.id, m.content)}
                className={`mt-2 flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded transition-colors ${
                  lm ? 'text-emerald-600 hover:bg-emerald-50' : 'text-emerald-400 hover:bg-emerald-900/20'
                }`}
              >
                <PlusCircle size={10} />
                Add to Project
              </button>
            )}
            {m.metadata?.compliance_reasoning && (m.metadata.referenced_categories?.length || m.metadata.ai_reasoning_steps?.length) && (
              <ComplianceReasoningPanel
                locations={m.metadata.compliance_reasoning}
                aiSteps={m.metadata.ai_reasoning_steps}
                referencedCategories={m.metadata.referenced_categories}
                referencedLocations={m.metadata.referenced_locations}
              />
            )}
            {m.metadata?.affected_employees && m.metadata.affected_employees.length > 0 && (
              <div className={`mt-2 pt-2 border-t ${divider}`}>
                <span className={`text-[10px] ${metaText} uppercase tracking-wide`}>
                  Affected Employees ({m.metadata.affected_employees.reduce((s, a) => s + a.count, 0)})
                </span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {m.metadata.affected_employees.map((ae, i) => (
                    <span key={i} className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded border ${
                      lm
                        ? 'bg-purple-50 text-purple-700 border-purple-300'
                        : 'bg-purple-900/30 text-purple-300 border-purple-700/40'
                    }`}>
                      <span className="font-medium">{ae.count}</span>
                      <span className={lm ? 'text-purple-500' : 'text-purple-400/70'}>in</span>
                      <span>{ae.location}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {m.metadata?.compliance_gaps && (() => {
              const refCats = new Set(m.metadata.referenced_categories ?? [])
              if (refCats.size === 0) return null
              const filtered = m.metadata.compliance_gaps.filter(g => refCats.has(g.category))
              if (filtered.length === 0) return null
              return (
              <div className={`mt-2 pt-2 border-t ${divider}`}>
                <span className={`text-[10px] ${lm ? 'text-amber-600' : 'text-amber-500/80'} uppercase tracking-wide`}>
                  Policy Gaps ({filtered.length})
                </span>
                <div className="mt-1 space-y-1">
                  {filtered.map((g, i) => (
                    <div key={i} className={`text-[11px] px-2 py-1 rounded border ${
                      lm
                        ? 'text-amber-700 bg-amber-50 border-amber-300'
                        : 'text-amber-400/80 bg-amber-900/20 border-amber-700/30'
                    }`}>
                      No written policy found for <span className="font-medium">{g.label}</span> — required by governing jurisdiction
                    </div>
                  ))}
                </div>
              </div>
              )})()}
            {penalties.length > 0 && (
              <div className={`mt-2 pt-2 border-t ${divider}`}>
                <span className={`text-[10px] ${lm ? 'text-red-500' : 'text-red-400/70'} uppercase tracking-wide`}>
                  Enforcement Risk ({penalties.length})
                </span>
                <div className="mt-1 space-y-1">
                  {penalties.map((p, i) => (
                    <div key={i} className={`text-[11px] rounded px-2 py-1 border ${
                      lm
                        ? 'bg-red-50 border-red-200'
                        : 'bg-red-900/15 border-red-800/30'
                    }`}>
                      <span className={`font-medium capitalize ${lm ? 'text-red-700' : 'text-red-300'}`}>{p.category}</span>
                      <span className={lm ? 'text-red-600' : 'text-red-400/70'}> — {p.summary}</span>
                      {p.agency && <span className={metaText}> ({p.agency})</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {m.metadata?.payer_sources && m.metadata.payer_sources.length > 0 && (
              <div className={`mt-2 pt-2 border-t ${divider}`}>
                <span className={`text-[10px] ${metaText} uppercase tracking-wide`}>Sources ({m.metadata.payer_sources.length})</span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {m.metadata.payer_sources.map((s, si) => (
                    <span key={si} className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded ${
                      lm ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-800 text-zinc-400'
                    }`}>
                      <span className="text-emerald-500">{s.payer_name}</span>
                      {s.policy_number && <span className={lm ? 'text-zinc-400' : 'text-zinc-600'}>|</span>}
                      {s.policy_number && <span>{s.policy_number}</span>}
                      {s.source_url && (
                        <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="text-emerald-500 hover:text-emerald-400 ml-0.5">
                          view
                        </a>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          m.content
        )}
      </div>
    </div>
  )
})

export default MessageBubble
