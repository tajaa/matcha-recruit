import type { ChannelMember } from '../../api/channels'

export { detectMentionToken } from '../../utils/mentions'

// @-mention rendering — splits message content into plain-text + mention-chip
// nodes. Server stamps `mentioned_user_ids` on the broadcast payload so we can
// confirm a handle resolved to a real channel member; unresolved `@foo`
// substrings render as plain text.
const MENTION_PATTERN = /(?:^|\s)(@[A-Za-z0-9._-]{2,32})\b/g

export function handleFromEmail(email: string): string {
  return (email.split('@')[0] || '').toLowerCase()
}

export function renderMessageContent(
  content: string,
  members: ChannelMember[],
  mentionedUserIds: string[] | undefined,
  currentUserId: string | undefined,
): React.ReactNode {
  if (!content) return null
  const validHandles = new Set(
    members
      .filter((m) => !mentionedUserIds || mentionedUserIds.includes(m.user_id))
      .map((m) => handleFromEmail(m.email || ''))
      .filter(Boolean),
  )
  const parts: React.ReactNode[] = []
  let lastIdx = 0
  for (const match of content.matchAll(MENTION_PATTERN)) {
    const fullMatch = match[0]
    const handleToken = match[1]
    const handle = handleToken.slice(1).toLowerCase()
    const idx = match.index ?? 0
    const tokenStart = idx + (fullMatch.length - handleToken.length)
    if (tokenStart > lastIdx) parts.push(content.slice(lastIdx, tokenStart))
    if (validHandles.has(handle)) {
      const mentioned = members.find((m) => handleFromEmail(m.email || '') === handle)
      const isMe = mentioned?.user_id === currentUserId
      parts.push(
        <span
          key={`m-${tokenStart}`}
          className={
            isMe
              ? 'inline-block px-1 rounded bg-yellow-500/25 text-yellow-200 font-medium'
              : 'inline-block px-1 rounded bg-w-accent/20 text-w-accent-hi font-medium'
          }
        >
          {handleToken}
        </span>,
      )
    } else {
      parts.push(handleToken)
    }
    lastIdx = idx + fullMatch.length
  }
  if (lastIdx < content.length) parts.push(content.slice(lastIdx))
  return parts
}
