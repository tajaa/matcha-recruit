import React, { useMemo } from 'react'
import Markdown from 'react-markdown'
import type { MWMessage } from '../../types/matcha-work'
import ComplianceReasoningPanel from './ComplianceReasoningPanel'

const MessageBubble = React.memo(function MessageBubble({ message: m }: { message: MWMessage }) {
  const markdownContent = useMemo(() => <Markdown>{m.content}</Markdown>, [m.content])

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
