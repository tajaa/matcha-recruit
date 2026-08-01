import type { ChannelMessage } from './channels'

/**
 * (created_at, id) comparator — the server's ORDER BY, applied client-side so
 * every device converges on ONE order regardless of WS arrival order (two
 * uvicorn workers ⇒ near-simultaneous messages can arrive in different orders
 * on different sockets). Pending rows carry a local ISO timestamp and sort
 * where they were sent; a small clock skew is acceptable — the echo replaces
 * them with the server timestamp.
 */
export function compareMessages(a: ChannelMessage, b: ChannelMessage): number {
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

/**
 * Union of the in-memory list and a REST page (reconnect catch-up or older-
 * page prepend). Never clobbers: a WS message that landed while the fetch was
 * in flight survives (the old reconnect handler replaced the array, erasing
 * it on this device only — the reported cross-device divergence). Pending
 * rows reconcile by client_message_id, which REST now returns.
 */
export function mergeMessages(prev: ChannelMessage[], fetched: ChannelMessage[]): ChannelMessage[] {
  const fetchedById = new Set(fetched.map((m) => m.id))
  const fetchedByCmid = new Set(
    fetched.filter((m) => m.client_message_id).map((m) => m.client_message_id as string),
  )
  const out = fetched.slice()
  for (const m of prev) {
    if (fetchedById.has(m.id)) continue // server copy wins over local copy
    if (m.pending && m.client_message_id && fetchedByCmid.has(m.client_message_id)) continue // landed
    out.push(m) // WS arrival mid-fetch, an older page already loaded, or an unlanded pending
  }
  out.sort(compareMessages)
  return out
}

/** Insert one live WS message: reconcile the sender's optimistic pending row
 * by cmid, else dedup by id, always keeping (created_at, id) order. */
export function upsertMessage(prev: ChannelMessage[], msg: ChannelMessage): ChannelMessage[] {
  if (msg.client_message_id) {
    const idx = prev.findIndex((m) => m.client_message_id === msg.client_message_id && m.pending)
    if (idx >= 0) {
      const next = prev.slice()
      next[idx] = msg
      next.sort(compareMessages)
      return next
    }
  }
  if (prev.some((m) => m.id === msg.id)) return prev
  const next = [...prev, msg]
  next.sort(compareMessages)
  return next
}
