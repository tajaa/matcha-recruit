import React, { useMemo } from 'react'
import Markdown from 'react-markdown'
import type { MWMessage } from '../../types/matcha-work'
import ComplianceReasoningPanel from './ComplianceReasoningPanel'

function extractPenalties(reasoning: MWMessage['metadata']): { category: string; summary: string; agency: string }[] {
  if (!reasoning?.compliance_reasoning) return []
  const seen = new Set<string>()
  const results: { category: string; summary: string; agency: string }[] = []
  for (const loc of reasoning.compliance_reasoning) {
    for (const cat of loc.categories) {
      if (seen.has(cat.category)) continue
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

const MessageBubble = React.memo(function MessageBubble({ message: m }: { message: MWMessage }) {
  const markdownContent = useMemo(() => <Markdown>{m.content}</Markdown>, [m.content])
  const penalties = useMemo(() => extractPenalties(m.metadata), [m.metadata])

  return (
    <div className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] sm:max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
          m.role === 'user'
            ? 'bg-zinc-700 text-white whitespace-pre-wrap'
            : 'bg-zinc-800/60 text-zinc-200 border border-zinc-700/50 prose prose-sm prose-invert prose-zinc max-w-none overflow-x-auto'
        }`}
      >
        {m.role === 'assistant' ? (
          <>
            {markdownContent}
            {m.metadata?.compliance_reasoning && (
              <ComplianceReasoningPanel
                locations={m.metadata.compliance_reasoning}
                aiSteps={m.metadata.ai_reasoning_steps}
                referencedCategories={m.metadata.referenced_categories}
                referencedLocations={m.metadata.referenced_locations}
              />
            )}
            {m.metadata?.affected_employees && m.metadata.affected_employees.length > 0 && (
              <div className="mt-2 pt-2 border-t border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wide">
                  Affected Employees ({m.metadata.affected_employees.reduce((s, a) => s + a.count, 0)})
                </span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {m.metadata.affected_employees.map((ae, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 text-[11px] bg-purple-900/30 text-purple-300 border border-purple-700/40 px-2 py-0.5 rounded">
                      <span className="font-medium">{ae.count}</span>
                      <span className="text-purple-400/70">in</span>
                      <span>{ae.location}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {m.metadata?.compliance_gaps && m.metadata.compliance_gaps.length > 0 && (
              <div className="mt-2 pt-2 border-t border-zinc-800">
                <span className="text-[10px] text-amber-500/80 uppercase tracking-wide">
                  Policy Gaps ({m.metadata.compliance_gaps.length})
                </span>
                <div className="mt-1 space-y-1">
                  {m.metadata.compliance_gaps.map((g, i) => (
                    <div key={i} className="text-[11px] text-amber-400/80 bg-amber-900/20 border border-amber-700/30 px-2 py-1 rounded">
                      No written policy found for <span className="font-medium">{g.label}</span> — required by governing jurisdiction
                    </div>
                  ))}
                </div>
              </div>
            )}
            {penalties.length > 0 && (
              <div className="mt-2 pt-2 border-t border-zinc-800">
                <span className="text-[10px] text-red-400/70 uppercase tracking-wide">
                  Enforcement Risk ({penalties.length})
                </span>
                <div className="mt-1 space-y-1">
                  {penalties.map((p, i) => (
                    <div key={i} className="text-[11px] bg-red-900/15 border border-red-800/30 rounded px-2 py-1">
                      <span className="text-red-300 font-medium capitalize">{p.category}</span>
                      <span className="text-red-400/70"> — {p.summary}</span>
                      {p.agency && <span className="text-zinc-500"> ({p.agency})</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {m.metadata?.payer_sources && m.metadata.payer_sources.length > 0 && (
              <div className="mt-2 pt-2 border-t border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Sources ({m.metadata.payer_sources.length})</span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {m.metadata.payer_sources.map((s, si) => (
                    <span key={si} className="inline-flex items-center gap-1 text-[11px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
                      <span className="text-emerald-400">{s.payer_name}</span>
                      {s.policy_number && <span className="text-zinc-600">|</span>}
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
