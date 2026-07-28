import type { MatterMessage } from '../../../../api/legal-defense/legalDefense'

/** Which assistant message IS the memo — mirrors
 * services/pilots/legal_defense/matters.py:latest_memo: the newest assistant
 * message with a non-empty evidence_map, else the newest assistant message,
 * else null when the matter has no assistant turns yet. */
export function pickLatestMemo(messages: MatterMessage[]): MatterMessage | null {
  const assistant = messages.filter((m) => m.role === 'assistant')
  if (assistant.length === 0) return null
  const withEvidence = [...assistant].reverse().find((m) => (m.metadata?.evidence_map?.length ?? 0) > 0)
  return withEvidence ?? assistant[assistant.length - 1]
}

// Same pattern as pages/app/legal-defense/Console.tsx:176 — kept in sync
// deliberately rather than exported/shared, since that file's CID_TOKEN_RE
// is a local, non-exported const.
export const CID_TOKEN_RE = /\[?(incident|er_case|compliance_req|discipline|training|policy_ack|accommodation):([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]?/g

export type MemoToken = string | { type: string; id: string }

/** Splits memo text on inline cid tokens like "[incident:<uuid>]" into plain
 * strings and {type, id} tokens, for rendering as non-clickable pills (v1 —
 * no getEvidence fetch here, so no human-readable ref to show on click). */
export function tokenizeCids(text: string): MemoToken[] {
  const re = new RegExp(CID_TOKEN_RE)
  const parts: MemoToken[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push({ type: m[1], id: m[2] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}
