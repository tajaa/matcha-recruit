import type { AgentChatMetadata } from '../../types'

// Helpers for Espresso's agent-card chat messages (see AgentCardMessage.tsx).
// Kept out of the component file so it only exports components (fast refresh).

export function isAgentCardMessage(metadata: unknown): metadata is AgentChatMetadata {
  const m = metadata as AgentChatMetadata | undefined
  return !!m && (
    (m.kind === 'agent_card_result' && !!m.result)
    || (m.kind === 'agent_card_prompt' && !!m.view)
    || (m.kind === 'agent_card_receipt' && !!m.receipt)
    // Espresso assistant
    || (m.kind === 'agent_progress' && !!m.run_id)
    || (m.kind === 'agent_result' && !!m.result_v2)
    || (m.kind === 'agent_receipt' && !!m.action_receipt)
  )
}

/** Whether a question was asked by the assistant (answered by its owner),
 *  not by an agent card (a buy / card question, answered by the buyer). */
export function isAssistantPrompt(metadata: AgentChatMetadata): boolean {
  return metadata.prompt_kind === 'ask_user' || metadata.prompt_kind === 'confirm_action'
}

/** Strip the leading `⟦ticket:id|title|column⟧` marker; returns the title too. */
export function splitTicketToken(content: string): { title: string | null; body: string } {
  const match = /^⟦ticket:[^|⟧]*\|([^|⟧]*)(?:\|[^⟧]*)?⟧\n?/.exec(content)
  if (!match) return { title: null, body: content }
  return { title: match[1] || null, body: content.slice(match[0].length) }
}
