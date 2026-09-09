import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, Paperclip, Send, Trash2 } from 'lucide-react'
import type { MissingItem, PublicSpec, SpecField, SymlinkAttachment } from '../../types/symlink'

// The recipient-facing "tunnel chat" + the schema-driven review form. Copies
// the bubble/composer markup of components/ir/IRPublicChatIntake.tsx but
// renders the review step from the link's spec instead of hard-coded fields.

const INPUT = 'mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-700 focus:outline-none'

type Props = {
  spec: PublicSpec
  companyName?: string | null
  title: string
  messages: { role: 'assistant' | 'user'; content: string }[]
  fields: Record<string, unknown>
  attachments: SymlinkAttachment[]
  missing: MissingItem[]
  complete: boolean
  sending: boolean
  uploading: string | null
  error: string | null
  mode: 'chat' | 'review'
  onSend: (text: string) => void
  onUpload: (slot: string, file: File) => void
  onRemoveAttachment: (id: string) => void
  onReview: () => void
  onBackToChat: () => void
  onSubmit: (fields: Record<string, unknown>) => void
  submitting: boolean
}

export function GuidedChat(props: Props) {
  const { spec, mode } = props
  if (mode === 'review') return <ReviewForm {...props} />

  return <ChatPane {...props} spec={spec} />
}

function AttachmentSlots({ spec, attachments, uploading, onUpload, onRemoveAttachment, compact }: Pick<Props, 'spec' | 'attachments' | 'uploading' | 'onUpload' | 'onRemoveAttachment'> & { compact?: boolean }) {
  if (spec.attachments.length === 0) return null
  return (
    <div className={`space-y-2 ${compact ? '' : 'rounded border border-zinc-800 bg-zinc-900/60 p-3'}`}>
      {!compact && <p className="text-[10px] uppercase tracking-widest text-zinc-500">Files</p>}
      {spec.attachments.map((slot) => {
        const file = attachments.find((a) => a.slot === slot.slot)
        const busy = uploading === slot.slot
        const inputId = `symlink-file-${slot.slot}`
        return (
          <div key={slot.slot} className="flex items-center justify-between gap-2 text-sm">
            <span className="min-w-0 truncate text-zinc-300">
              {file ? <Check className="mr-1 inline h-3.5 w-3.5 text-emerald-500" /> : null}
              {slot.label}{slot.required && !file && <span className="text-amber-400"> *</span>}
              {file && <span className="ml-1 text-zinc-500">· {file.file_name}</span>}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <label htmlFor={inputId} className={`inline-flex cursor-pointer items-center gap-1 rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:border-emerald-700 ${busy ? 'opacity-60' : ''}`}>
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Paperclip className="h-3 w-3" />} {file ? 'Replace' : 'Upload'}
              </label>
              <input id={inputId} type="file" className="hidden" accept={(slot.accept ?? []).join(',')} disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(slot.slot, f); e.target.value = '' }} />
              {file && <button type="button" onClick={() => onRemoveAttachment(file.id)} className="text-zinc-500 hover:text-red-400" aria-label="Remove file"><Trash2 className="h-3.5 w-3.5" /></button>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ChatPane({ spec, companyName, title, messages, sending, error, complete, missing, onSend, onReview, ...rest }: Props) {
  const [message, setMessage] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages.length, sending])

  function send(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim()) return
    onSend(message)
    setMessage('')
  }

  return (
    <div className="space-y-4 text-left">
      <div className="text-center">
        <h1 className="text-lg font-semibold text-zinc-100">{title}</h1>
        {companyName && <p className="mt-1 text-sm text-zinc-400">{companyName}</p>}
        {spec.goal && <p className="mt-2 text-xs text-zinc-500">{spec.goal}</p>}
      </div>
      <div ref={scrollRef} className="max-h-[44vh] space-y-2.5 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/40 p-3">
        {messages.map((entry, index) => (
          <div key={index} className={`flex ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] rounded-xl px-3 py-2 text-sm ${entry.role === 'user' ? 'border border-emerald-500/25 bg-emerald-500/15 text-zinc-100' : 'border border-zinc-800 bg-zinc-900 text-zinc-200'}`}>{entry.content}</div>
          </div>
        ))}
        {sending && <div className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking...</div>}
      </div>
      <AttachmentSlots spec={spec} attachments={rest.attachments} uploading={rest.uploading} onUpload={rest.onUpload} onRemoveAttachment={rest.onRemoveAttachment} />
      {error && <p className="text-sm text-amber-300">{error}</p>}
      <form onSubmit={send} className="flex gap-2">
        <input autoFocus value={message} onChange={(e) => setMessage(e.target.value)} disabled={sending} maxLength={600} placeholder="Type your reply..." className="min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-700 focus:outline-none" />
        <button type="submit" disabled={!message.trim() || sending} className="flex h-10 w-10 items-center justify-center rounded bg-emerald-700 text-white disabled:opacity-50" aria-label="Send"><Send className="h-4 w-4" /></button>
      </form>
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>{complete ? 'Everything required is in.' : missing.length ? `Still needed: ${missing.map((m) => m.label).join(', ')}` : ''}</span>
        <button type="button" onClick={onReview} className={`underline ${complete ? 'text-emerald-400' : 'text-zinc-400'} hover:text-zinc-200`}>{complete ? 'Review and send' : 'Review what I have'}</button>
      </div>
    </div>
  )
}

function FieldInput({ field, value, onChange }: { field: SpecField; value: unknown; onChange: (v: string) => void }) {
  const str = value === null || value === undefined ? '' : String(value)
  if (field.type === 'long_text') {
    return <textarea value={str} onChange={(e) => onChange(e.target.value)} rows={4} maxLength={field.max_len ?? 4000} className={INPUT} />
  }
  if (field.type === 'choice' && field.choices?.length) {
    return (
      <select value={str} onChange={(e) => onChange(e.target.value)} className={INPUT}>
        <option value="">Choose…</option>
        {field.choices.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  }
  return <input value={str} onChange={(e) => onChange(e.target.value)} maxLength={field.max_len ?? 255} inputMode={field.type === 'number' ? 'decimal' : undefined} className={INPUT} />
}

function ReviewForm({ spec, fields, attachments, error, onBackToChat, onSubmit, submitting, ...rest }: Props) {
  // Seeded once: GuidedChat only renders ReviewForm while mode === 'review', so
  // every entry into review mounts a fresh form over the latest fields.
  const [draft, setDraft] = useState<Record<string, unknown>>(fields)
  const [honeypot, setHoneypot] = useState('')

  const missingFields = spec.fields.filter((f) => f.required && !String(draft[f.key] ?? '').trim())
  const missingFiles = spec.attachments.filter((a) => a.required && !attachments.some((x) => x.slot === a.slot))
  const ready = missingFields.length === 0 && missingFiles.length === 0

  return (
    <div className="space-y-4 text-left">
      <div className="rounded border border-emerald-900/40 bg-emerald-950/20 p-3 text-sm text-emerald-100">Review before sending. You can edit every answer.</div>
      {spec.fields.map((f) => (
        <label key={f.key} className="block">
          <span className="text-xs uppercase tracking-wide text-zinc-400">{f.label}{!f.required && <span className="ml-1 normal-case tracking-normal text-zinc-600">(optional)</span>}</span>
          <FieldInput field={f} value={draft[f.key]} onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))} />
          {f.hint && <span className="mt-1 block text-[11px] text-zinc-500">{f.hint}</span>}
        </label>
      ))}
      <AttachmentSlots spec={spec} attachments={attachments} uploading={rest.uploading} onUpload={rest.onUpload} onRemoveAttachment={rest.onRemoveAttachment} />
      {/* Honeypot — hidden from humans; bots that fill it get a silent "success". */}
      <input type="text" name="internal_ref" tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} className="hidden" aria-hidden="true" />
      {!ready && <p className="text-xs text-amber-300">Still needed: {[...missingFields.map((f) => f.label), ...missingFiles.map((a) => a.label)].join(', ')}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button type="button" onClick={() => onSubmit(draft)} disabled={!ready || submitting} className="flex w-full items-center justify-center rounded bg-emerald-700 py-2.5 font-medium text-white transition hover:bg-emerald-600 disabled:opacity-50">{submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : spec.submit_label || 'Send'}</button>
      <button type="button" onClick={onBackToChat} className="w-full text-xs text-zinc-500 underline hover:text-zinc-300">Continue chat</button>
    </div>
  )
}
