// Chat state for the flyer design assistant.
//
// Owns the transcript and the in-flight flag; the DOCUMENT stays with the
// designer page, which is what pushes a turn's result through undo history. The
// hook never touches the document directly — it asks, and hands back what came.
import { useCallback, useRef, useState } from 'react'
import { flyerAiApi } from '../api/flyerAi'
import type { AssistHistoryTurn, AssistSelection } from '../api/flyerAi'
import type { FlyerDesign, FlyerIdea, FlyerOpResult } from '../api/types'

// Turns of context sent back up. Assistant turns carry a compact recap of what
// they changed instead of the raw ops — the model needs to know "you moved the
// QR last turn", not the JSON that did it, and the full op log would grow the
// prompt without bound.
const HISTORY_TURNS = 10

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  results?: FlyerOpResult[]
  rejected?: { reason: string }[]
}

export interface FlyerAssistantOptions {
  campaignId: string
  getDesign: () => FlyerDesign
  /** Applied by the caller through its own history, so one turn = one undo step. */
  onDesign: (next: FlyerDesign) => void
  getSelection: () => AssistSelection | undefined
}

function messageId() {
  return crypto.randomUUID()
}

function summarise(results: FlyerOpResult[]): string | undefined {
  const done = results.filter((r) => r.ok).map((r) => r.summary)
  return done.length ? done.join('; ').slice(0, 2000) : undefined
}

export function useFlyerAssistant({ campaignId, getDesign, onDesign, getSelection }: FlyerAssistantOptions) {
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [ideas, setIdeas] = useState<FlyerIdea[]>([])
  const [ideasLoading, setIdeasLoading] = useState(false)

  // The transcript as the SERVER should see it, kept alongside the rendered
  // messages so a re-render can't desync the two.
  const history = useRef<AssistHistoryTurn[]>([])
  // Guards against a double submit landing two turns against the same document —
  // the second would be built from a snapshot the first is about to replace.
  const inFlight = useRef(false)

  const send = useCallback(async (text: string) => {
    const message = text.trim()
    if (!message || inFlight.current) return
    inFlight.current = true
    setSending(true)
    setError('')
    setMessages((m) => [...m, { id: messageId(), role: 'user', content: message }])

    try {
      const res = await flyerAiApi.assist(campaignId, {
        message,
        design: getDesign(),
        history: history.current.slice(-HISTORY_TURNS * 2),
        selection: getSelection(),
      })
      history.current = [
        ...history.current,
        { role: 'user', content: message },
        { role: 'assistant', content: res.message, ops_summary: summarise(res.results) },
      ]
      setMessages((m) => [...m, {
        id: messageId(),
        role: 'assistant',
        content: res.message,
        results: res.results,
        rejected: res.rejected,
      }])
      // Adopted even when `ops` is empty: the server echoes the document back
      // unchanged in that case, so this stays a single code path.
      onDesign(res.design)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The assistant could not be reached.')
    } finally {
      inFlight.current = false
      setSending(false)
    }
  }, [campaignId, getDesign, onDesign, getSelection])

  const loadIdeas = useCallback(async () => {
    setIdeasLoading(true)
    setError('')
    try {
      const { ideas: got } = await flyerAiApi.ideas(campaignId)
      setIdeas(got)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not generate ideas.')
    } finally {
      setIdeasLoading(false)
    }
  }, [campaignId])

  const applyIdea = useCallback((idea: FlyerIdea) => {
    onDesign(idea.design)
    // Recorded in the transcript so a follow-up ("make that one warmer") has
    // something to refer back to.
    history.current = [...history.current, {
      role: 'assistant', content: `Applied the "${idea.label}" layout.`, ops_summary: 'Rebuilt the flyer',
    }]
    setMessages((m) => [...m, {
      id: messageId(), role: 'assistant', content: `Applied the "${idea.label}" layout.`,
    }])
  }, [onDesign])

  return { messages, sending, error, send, ideas, ideasLoading, loadIdeas, applyIdea }
}
