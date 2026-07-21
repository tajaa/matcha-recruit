import { useCallback, type Dispatch, type SetStateAction } from 'react'

/**
 * Generate a client-side temporary message id. Prefers `crypto.randomUUID()`;
 * falls back to a timestamp+random string where it is unavailable.
 */
export function makeTempId(prefix = 'tmp'): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/**
 * Shared optimistic-message primitives for the two chat surfaces (channel view +
 * matcha-work thread). Deliberately owns ONLY what is common between them — the
 * guarded optimistic append and the replace-temp-by-id reconcile — and leaves the
 * reconcile *trigger* to each caller, because they genuinely differ: ChannelView
 * reconciles off a WebSocket echo (keyed on `client_message_id`, with a loopback-race
 * guard), while the thread controller reconciles off the HTTP response of the same
 * send call (replacing one temp with the returned user + assistant messages).
 */
export function useOptimisticMessages<T extends { id: string }>(
  setMessages: Dispatch<SetStateAction<T[]>>,
) {
  /**
   * Append an optimistic message. When `dedupeBy` is supplied and already matches an
   * existing message, the append is skipped — this is the loopback-race guard for
   * surfaces where a server echo can arrive before this updater runs.
   */
  const appendOptimistic = useCallback(
    (msg: T, dedupeBy?: (m: T) => boolean) => {
      setMessages((prev) => (dedupeBy && prev.some(dedupeBy) ? prev : [...prev, msg]))
    },
    [setMessages],
  )

  /**
   * Replace the temp message with `tempId` by one or more real (server) messages.
   */
  const reconcileById = useCallback(
    (tempId: string, ...real: T[]) => {
      setMessages((prev) => [...prev.filter((m) => m.id !== tempId), ...real])
    },
    [setMessages],
  )

  return { appendOptimistic, reconcileById }
}
