import { useEffect, useRef, useState } from 'react'
import { Bot, Loader2, Send, Sparkles, X } from 'lucide-react'
import { useToast } from '../../ui'
import { getScheduleHuumeSession } from '../../../api/employees/scheduleChat'
import { sendMessageStream } from '../../../work/api/matchaWork/messaging'
import type { HuumeStep, MWMessage, MWSendResponse, MWStreamEvent } from '../../../work/types'
import HuumeStepTimeline from '../../../work/components/panels/HuumeStepTimeline'

interface ScheduleHuumePanelProps {
  firstName: string
  weekStart: string
  locationId: string | null
  locationName?: string
  onApplied(): void
  onClose(): void
}

type PanelMessage = { id: string; role: 'user' | 'assistant'; content: string; steps?: HuumeStep[] }

function fromMessage(message: MWMessage): PanelMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    steps: message.metadata?.huume_steps || undefined,
  }
}

function changedSchedule(response: MWSendResponse): boolean {
  const state = response.current_state || {}
  const action = state.huume_action as Record<string, unknown> | undefined
  return Boolean(action && ['applied', 'created', 'updated'].includes(String(action.status)))
}

export default function ScheduleHuumePanel({ firstName, weekStart, locationId, locationName, onApplied, onClose }: ScheduleHuumePanelProps) {
  const { toast } = useToast()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<PanelMessage[]>([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('')
  const [steps, setSteps] = useState<HuumeStep[]>([])
  const [busy, setBusy] = useState(false)
  const mounted = useRef(true)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    mounted.current = true
    setThreadId(null)
    setMessages([])
    setStatus('Opening the schedule workspace…')
    if (locationId) {
      void getScheduleHuumeSession(locationId, weekStart)
        .then((session) => {
          if (!mounted.current) return
          setThreadId(session.thread_id)
          setMessages(session.messages.map(fromMessage))
          setStatus('')
        })
        .catch((error) => {
          if (mounted.current) {
            setStatus('')
            toast(error instanceof Error ? error.message : 'Could not open the schedule assistant', 'error')
          }
        })
    } else {
      setStatus('Choose a location to start the schedule assistant.')
    }
    return () => {
      mounted.current = false
      abortRef.current?.abort()
    }
  }, [locationId, weekStart, toast])

  function send() {
    const content = input.trim()
    if (!content || !threadId || busy) return
    setInput('')
    setBusy(true)
    setStatus('Huume is working…')
    setSteps([])
    const tempId = `temp-${Date.now()}`
    setMessages((current) => [...current, { id: tempId, role: 'user', content }])
    abortRef.current = sendMessageStream(threadId, content, {
      onEvent: (event: MWStreamEvent) => {
        if (!mounted.current) return
        if (event.type === 'status') setStatus(event.message)
        if (event.type === 'step') setSteps((current) => [...current, event.data])
      },
      onComplete: (response: MWSendResponse) => {
        if (!mounted.current) return
        setMessages((current) => [
          ...current.filter((message) => message.id !== tempId),
          fromMessage(response.user_message),
          { ...fromMessage(response.assistant_message), steps: response.assistant_message.metadata?.huume_steps || steps },
        ])
        setSteps([])
        setStatus('')
        setBusy(false)
        if (changedSchedule(response)) onApplied()
      },
      onError: (message: string) => {
        if (!mounted.current) return
        setStatus('')
        setBusy(false)
        toast(message, 'error')
      },
    })
  }

  return (
    <section className="absolute left-1/2 top-2 z-30 flex w-[min(460px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950/95 shadow-2xl backdrop-blur">
      <header className="flex items-center gap-2 border-b border-white/[0.08] px-3 py-2">
        <Sparkles className="h-4 w-4 text-emerald-300" />
        <span className="text-xs font-medium text-zinc-200">Huume · Schedule assistant</span>
        <span className="ml-auto text-[10px] text-zinc-600">{locationName || 'Location'} · {weekStart}</span>
        <button onClick={onClose} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close schedule assistant"><X className="h-4 w-4" /></button>
      </header>
      <div className="flex max-h-[min(560px,70vh)] min-h-[220px] flex-col gap-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && <div className="text-xs text-zinc-400">Hi, {firstName}. What would you like to understand or change in this week’s schedule?</div>}
        {messages.map((message) => (
          <div key={message.id} className={message.role === 'user' ? 'ml-8 rounded-lg bg-emerald-950/50 px-3 py-2 text-xs text-emerald-100' : 'mr-4 rounded-lg bg-white/[0.05] px-3 py-2 text-xs leading-relaxed text-zinc-200'}>
            <div className="flex items-start gap-2"><Bot className={message.role === 'assistant' ? 'mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300' : 'hidden'} /><span className="whitespace-pre-wrap">{message.content}</span></div>
            {message.steps && <HuumeStepTimeline steps={message.steps} />}
          </div>
        ))}
        {steps.length > 0 && <div className="mr-4 rounded-lg bg-white/[0.03] px-3 py-2"><HuumeStepTimeline steps={steps} live /></div>}
        {status && <div className="flex items-center gap-2 text-[11px] text-zinc-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />{status}</div>}
      </div>
      <form onSubmit={(event) => { event.preventDefault(); send() }} className="flex items-center gap-2 border-t border-white/[0.08] p-2">
        <input value={input} onChange={(event) => setInput(event.target.value)} disabled={!threadId || busy} placeholder="Try: add an opener Monday" className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-zinc-100 outline-none placeholder:text-zinc-600" />
        <button type="submit" disabled={!threadId || busy || !input.trim()} className="rounded-lg bg-emerald-500 p-2 text-zinc-950 disabled:opacity-40" aria-label="Send scheduling question"><Send className="h-4 w-4" /></button>
      </form>
    </section>
  )
}
