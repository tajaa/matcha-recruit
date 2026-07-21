import { useEffect, useRef, useState } from 'react'

/**
 * Shared lifecycle for the grounded pilot chat consoles (analysis-pilot,
 * handbook-pilot — the two whose send loop is identical). Owns the parts that were
 * byte-identical between them: the messages/input/busy/status state, the scroll +
 * abort refs, the abort-on-unmount and scroll-to-bottom effects, and `runTurn` — the
 * busy/status/AbortController/try-finally wrapper around one streamed turn.
 *
 * It deliberately does NOT own the turn *content* (the streamChat call, its per-pilot
 * extra args like focus cids, the optimistic user message, or the result→message
 * mapping) — those genuinely differ per console, so each `send` keeps its own body and
 * just wraps the streaming call in `runTurn`.
 */
export function usePilotChat<TMsg>({
  initialMessages,
  statusLabel,
  onTurn,
}: {
  initialMessages: TMsg[]
  statusLabel: string
  onTurn: () => void
}) {
  const [messages, setMessages] = useState<TMsg[]>(initialMessages)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Abort any in-flight turn when the user switches sessions (unmount).
  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, status])

  /**
   * Run one streamed turn. Sets busy + the status label, hands `turn` an AbortSignal
   * and a `markError` flag, and on completion restores busy/status and fires `onTurn`
   * — unless the turn was aborted (unmount/session switch), which skips the reset so a
   * ghost message and stuck composer don't appear.
   */
  const runTurn = async (
    turn: (signal: AbortSignal, markError: () => void) => Promise<void>,
  ) => {
    setBusy(true)
    setStatus(statusLabel)
    const controller = new AbortController()
    abortRef.current = controller
    let hadError = false
    try {
      await turn(controller.signal, () => { hadError = true })
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false)
        if (!hadError) setStatus(null) // keep the error visible; clear only on success
        onTurn()
      }
    }
  }

  return {
    messages, setMessages,
    input, setInput,
    busy, status, setStatus,
    scrollRef, abortRef, textareaRef,
    runTurn,
  }
}
