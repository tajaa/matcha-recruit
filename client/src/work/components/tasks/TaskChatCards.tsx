import { useRef, useState } from 'react'
import { Link, useInRouterContext } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, ChevronRight, ClipboardList, FileText, Hand, Image as ImageIcon, Loader2, PlayCircle, X,
} from 'lucide-react'
import { answerAgentTaskForm } from '../../api/matchaWork/agentTasks'
import { privateInputId } from '../../api/matchaWork/assistant'
import { uploadChannelFiles } from '../../api/channels'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type { AgentTaskCard, IntakeForm, IntakeFormField } from '../../types'
import IntakeFieldInput from './IntakeFieldInput'
import ResumeFormField from '../resume/ResumeFormField'
import { useMyResume } from '../../hooks/useMyResume'
import { buildFormValues, cardFacts, formErrorText, initialText, taskCardBody, taskCardLead, webUrl } from './tasksLogic'

// Espresso Tasks in the conversation, as on the Mac (`TaskChatCards.swift`):
// the card a task posts where it started (and again when it ends), and the
// form Espresso asks a task's details with.

/** A link into Tasks: a router Link inside the app, a plain link outside it. */
function AppLink({ to, className, children }: { to: string; className: string; children: React.ReactNode }) {
  return useInRouterContext()
    ? <Link to={to} className={className}>{children}</Link>
    : <a href={to} className={className}>{children}</a>
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="space-y-2.5 rounded-2xl border border-w-line bg-w-surface p-3">{children}</div>
}

function TaskIcon({ card }: { card: AgentTaskCard }) {
  const tone = card.status === 'failed' ? 'text-amber-500' : 'text-w-accent'
  if (card.event === 'started') return <PlayCircle size={13} className={tone} />
  switch (card.status) {
    case 'done': return <CheckCircle2 size={13} className={tone} />
    case 'failed': return <AlertTriangle size={13} className={tone} />
    case 'waiting': return <Hand size={13} className={tone} />
    default: return <ClipboardList size={13} className={tone} />
  }
}

/** "On it" when a task starts; the headline and top findings when it ends. */
export function TaskCard({ card }: { card: AgentTaskCard }) {
  const base = useWorkBase()
  const body = taskCardBody(card)
  const taskPath = `${base}/tasks/${encodeURIComponent(card.task_id)}`
  return (
    <Shell>
      <p className="flex items-center gap-1.5 text-[11px] font-semibold text-w-dim">
        <TaskIcon card={card} /> {taskCardLead(card)}
      </p>
      {card.title && <p className="text-sm font-semibold text-w-text">{card.title}</p>}
      {body && <p className="text-xs leading-5 text-w-dim">{body}</p>}
      {(card.items ?? []).map((item) => {
        const image = webUrl(item.image)
        const facts = cardFacts(item.fields)
        return (
          <AppLink
            key={item.id}
            to={`${taskPath}?item=${encodeURIComponent(item.id)}`}
            className="flex items-start gap-2 rounded-lg p-1 hover:bg-w-surface2/60"
          >
            {image && <img src={image} alt="" loading="lazy" className="h-10 w-10 shrink-0 rounded-md object-cover" />}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-semibold text-w-text">{item.title}</span>
              {item.subtitle && <span className="block truncate text-[11px] text-w-dim">{item.subtitle}</span>}
              {facts && <span className="block truncate text-[10px] text-w-dim">{facts}</span>}
            </span>
            <ChevronRight size={12} className="mt-1 shrink-0 text-w-faint" />
          </AppLink>
        )
      })}
      <AppLink to={taskPath} className="inline-flex items-center gap-1 text-[11px] font-medium text-w-accent hover:underline">
        <ClipboardList size={12} /> Open in Tasks
      </AppLink>
    </Shell>
  )
}

/** Fill in a task's details and start it. Its owner fills and submits it
 *  (the task starts with no model run); anyone can still just reply. */
export function IntakeFormCard({ question, form, promptId, status, closedText, mine, channelId }: {
  question: string
  form: IntakeForm
  promptId?: string
  /** open / answered / superseded / expired. */
  status: string
  closedText: string
  mine: boolean
  /** The conversation it is in: a form's files upload there, privately. */
  channelId?: string
}) {
  const base = useWorkBase()
  const fields = form.fields ?? []
  const [text, setText] = useState<Record<string, string>>(() => Object.fromEntries(
    fields.flatMap((f) => (initialText(f.value) ? [[f.key, initialText(f.value)]] : [])),
  ))
  const [files, setFiles] = useState<Record<string, File[]>>({})
  const [agreed, setAgreed] = useState(false)
  const [sending, setSending] = useState(false)
  const [problems, setProblems] = useState<string[]>([])
  const [startedTaskId, setStartedTaskId] = useState<string | null>(null)
  const units = form.units ?? 0
  const resumeField = fields.find((f) => f.widget === 'resume')
  const { resume } = useMyResume(!!resumeField)

  async function submit() {
    if (!promptId || sending) return
    const built = buildFormValues(fields, text, files)
    if (resumeField && text[resumeField.key] === 'yes' && !resume) {
      built.problems.push('Drop in your résumé, or switch “Use my résumé” off for a general search.')
    }
    setProblems(built.problems)
    if (built.problems.length) return
    setSending(true)
    try {
      const pending = Object.values(files).flat()
      let inputIds: string[] = []
      if (pending.length) {
        if (!channelId) { setProblems(["Files can't be added here."]); return }
        const uploaded = await uploadChannelFiles(channelId, pending)
        inputIds = uploaded.map((a) => privateInputId(a.url)).filter((id): id is string => !!id)
      }
      const task = await answerAgentTaskForm(promptId, {
        values: built.values, input_ids: inputIds, consent_version: form.consent?.version ?? null,
      })
      setStartedTaskId(task.id)
    } catch (e) {
      setProblems([formErrorText(e, "Couldn't start it. Try again in a moment.")])
    } finally {
      setSending(false)
    }
  }

  let footer: React.ReactNode
  if (startedTaskId) {
    footer = (
      <p className="flex flex-wrap items-center gap-2 text-[11px] font-medium text-w-accent">
        <CheckCircle2 size={12} /> Started
        <AppLink to={`${base}/tasks/${encodeURIComponent(startedTaskId)}`} className="hover:underline">Open in Tasks</AppLink>
      </p>
    )
  } else if (status !== 'open') {
    footer = <p className="flex items-center gap-1.5 text-[11px] text-w-dim"><CheckCircle2 size={12} /> {closedText}</p>
  } else if (!mine) {
    footer = <p className="text-[11px] text-w-dim">Waiting for the person it asked.</p>
  } else {
    footer = (
      <>
        <div className="space-y-2.5">
          {fields.map((field) => (
            <div key={field.key} className="space-y-1">
              <label htmlFor={`form-${promptId}-${field.key}`} className="block text-[11px] font-medium text-w-text">
                {field.label}{field.optional ? ' (optional)' : ''}
              </label>
              {field.type === 'file' ? (
                <FileField
                  field={field}
                  files={files[field.key] ?? []}
                  onChange={(next) => setFiles((prev) => ({ ...prev, [field.key]: next }))}
                  onProblem={(problem) => setProblems([problem])}
                />
              ) : field.type === 'consent' ? null : (
                <IntakeFieldInput
                  id={`form-${promptId}-${field.key}`}
                  field={field}
                  value={text[field.key] ?? ''}
                  onChange={(value) => setText((prev) => ({ ...prev, [field.key]: value }))}
                />
              )}
              {field.widget === 'resume' && <ResumeFormField on={text[field.key] === 'yes'} />}
              {field.help && <p className="text-[10px] text-w-dim">{field.help}</p>}
            </div>
          ))}
        </div>
        {form.consent && (
          <div className="space-y-1 rounded-lg bg-w-surface2/60 p-2.5">
            <p className="text-[11px] font-semibold text-w-text">{form.consent.title}</p>
            {form.consent.body.map((line) => <p key={line} className="text-[10px] leading-4 text-w-dim">{line}</p>)}
            <label className="flex items-center gap-1.5 pt-1 text-[11px] text-w-text">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} /> I agree
            </label>
          </div>
        )}
        {problems.map((problem) => <p key={problem} role="alert" className="text-[11px] text-amber-500">{problem}</p>)}
        <div className="flex items-center gap-2">
          <p className="flex-1 text-[10px] text-w-dim">Or just reply here.</p>
          {sending && <Loader2 size={13} className="animate-spin text-w-dim" />}
          <button
            type="button"
            onClick={() => void submit()}
            disabled={sending || !promptId || (!!form.consent && !agreed)}
            className="rounded-lg bg-w-accent px-3 py-1.5 text-xs font-semibold text-w-on-accent hover:opacity-90 disabled:opacity-50"
          >
            {form.submit_label || 'Start'}
          </button>
        </div>
      </>
    )
  }

  return (
    <Shell>
      <p className="text-sm font-semibold text-w-text">{question}</p>
      <p className="text-[10px] text-w-dim">
        {units > 0 ? `${form.label} · uses ${units} units when it starts` : form.label}
      </p>
      {(form.known ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {(form.known ?? []).map((k) => (
            <span key={k.key} className="rounded-full bg-w-accent/10 px-2 py-0.5 text-[10px] font-medium text-w-text">
              {k.label}: {k.shown}
            </span>
          ))}
        </div>
      )}
      {footer}
    </Shell>
  )
}

/** What a file field takes, as the browser's file picker understands it. */
function acceptFor(accept: string[] | undefined): string | undefined {
  const types: string[] = []
  if (accept?.includes('image')) types.push('image/png', 'image/jpeg', 'image/webp', 'image/heic')
  if (accept?.includes('document')) types.push('.pdf', '.txt', '.csv', '.json', '.docx', '.doc', '.md')
  return types.length ? types.join(',') : undefined
}

function FileField({ field, files, onChange, onProblem }: {
  field: IntakeFormField
  files: File[]
  onChange: (files: File[]) => void
  onProblem: (problem: string) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const max = field.max_count ?? 1
  const maxBytes = field.max_bytes ?? 0
  function add(picked: FileList | null) {
    const next = [...files]
    for (const file of Array.from(picked ?? [])) {
      if (next.length >= max) break
      if (maxBytes > 0 && file.size > maxBytes) {
        onProblem(`${file.name} is larger than ${Math.floor(maxBytes / 1_048_576)} MB.`)
        continue
      }
      next.push(file)
    }
    onChange(next)
    if (input.current) input.current.value = ''
  }
  return (
    <div className="space-y-1">
      {files.map((file, i) => (
        <p key={`${file.name}-${i}`} className="flex items-center gap-1.5 text-[11px] text-w-dim">
          {file.type.startsWith('image/') ? <ImageIcon size={11} /> : <FileText size={11} />}
          <span className="truncate">{file.name}</span>
          <button type="button" aria-label={`Remove ${file.name}`} onClick={() => onChange(files.filter((_, j) => j !== i))} className="text-w-faint hover:text-w-text">
            <X size={11} />
          </button>
        </p>
      ))}
      {files.length < max && (
        <>
          <input ref={input} type="file" multiple={max > 1} accept={acceptFor(field.accept)} className="hidden" onChange={(e) => add(e.target.files)} />
          <button type="button" onClick={() => input.current?.click()} className="rounded-md border border-w-line px-2 py-1 text-[11px] text-w-text hover:bg-w-surface2">
            Add file…
          </button>
        </>
      )}
    </div>
  )
}
