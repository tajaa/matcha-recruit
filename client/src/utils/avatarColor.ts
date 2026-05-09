/**
 * Deterministic per-user color from a 7-color palette. Same hash output as
 * the local copy in ThreadCollaborators.tsx so cursor color matches the user
 * avatar color across the app. Reuse via this util for any new presence
 * surface (RemoteCursor, RemoteCaret, CollaboratorsPill).
 */

const AVATAR_COLORS = ['#ce9178', '#569cd6', '#b5cea8', '#dcdcaa', '#c586c0', '#4ec9b0', '#9cdcfe']

export function avatarColor(userId: string): string {
  let hash = 0
  for (let i = 0; i < userId.length; i++) {
    hash = ((hash << 5) - hash + userId.charCodeAt(i)) | 0
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}
