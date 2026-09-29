import type { AgentChatMetadata } from '../../types'

// Helpers for Espresso's agent-card chat messages (see AgentCardMessage.tsx).
// Kept out of the component file so it only exports components (fast refresh).

export function isAgentCardMessage(metadata: unknown): metadata is AgentChatMetadata {
  const m = metadata as AgentChatMetadata | undefined
  return !!m && (
    (m.kind === 'agent_card_result' && !!m.result)
    || (m.kind === 'agent_card_prompt' && !!m.view)
    || (m.kind === 'agent_card_receipt' && !!m.receipt)
  )
}

/** Strip the leading `⟦ticket:id|title|column⟧` marker; returns the title too. */
export function splitTicketToken(content: string): { title: string | null; body: string } {
  const match = /^⟦ticket:[^|⟧]*\|([^|⟧]*)(?:\|[^⟧]*)?⟧\n?/.exec(content)
  if (!match) return { title: null, body: content }
  return { title: match[1] || null, body: content.slice(match[0].length) }
}
