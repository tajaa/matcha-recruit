// The banner after the Meta Connect round trip. The server's callback sends
// codes — the platforms connected, the permissions not granted, how many
// accounts came in with their inbox off — and the words are written here, so a
// crafted link can't put its own text in front of the owner.

const PLATFORMS = new Set(['facebook', 'instagram'])

const SCOPE_LABELS: Record<string, string> = {
  pages_manage_posts: 'posting to Facebook',
  pages_manage_engagement: 'replying to Facebook comments',
  pages_messaging: 'Facebook messages',
  instagram_content_publish: 'posting to Instagram',
  instagram_manage_comments: 'Instagram comments',
  instagram_manage_messages: 'Instagram messages',
}

export type ConnectNotice = { tone: 'ok' | 'warn'; text: string }

export function connectNotice(params: URLSearchParams): ConnectNotice | null {
  const platforms = (params.get('connected') ?? '').split(',').filter((p) => PLATFORMS.has(p))
  if (platforms.length === 0) return null
  const text = `Connected ${platforms.join(' and ')}.`

  const notes: string[] = []
  const missing = [...new Set((params.get('social_missing') ?? '').split(',').map((s) => SCOPE_LABELS[s]).filter(Boolean))]
  if (missing.length > 0) {
    notes.push(`Meta didn’t allow ${missing.join(', ')}. Reconnect and allow it, or that won’t work.`)
  }
  const off = Number.parseInt(params.get('social_inbox_off') ?? '', 10)
  if (off > 0) {
    notes.push(`${off === 1 ? '1 account came' : `${off} accounts came`} in with its comments and messages off, `
      + 'since you manage several Pages. Turn on the store’s own under Accounts.')
  }
  return notes.length > 0 ? { tone: 'warn', text: `${text} ${notes.join(' ')}` } : { tone: 'ok', text }
}
