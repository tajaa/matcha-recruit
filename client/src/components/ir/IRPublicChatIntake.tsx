import { useEffect, useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { usePublicChatIntake } from '../../hooks/ir/usePublicChatIntake'
import type { PublicChatIntakeFields } from '../../types/ir'
import { SubmissionDisclaimer } from './SubmissionDisclaimer'

type Props = {
  kind: 'report' | 'intake'
  token: string
  companyName?: string | null
  locationLabel?: string
  submitting: boolean
  submitError: string | null
  onSubmit: (fields: PublicChatIntakeFields) => void
  reviewExtras?: React.ReactNode
}

const INPUT = 'mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-700 focus:outline-none'

export function IRPublicChatIntake({ kind, token, companyName, locationLabel, submitting, submitError, onSubmit, reviewExtras }: Props) {
  const chat = usePublicChatIntake(kind, token)
  const [draft, setDraft] = useState<PublicChatIntakeFields | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (chat.complete) setDraft(chat.fields)
  }, [chat.complete, chat.fields])

  const isReview = draft !== null
  const requiredComplete = kind === 'report'
    ? (draft?.description?.trim().length ?? 0) >= 10
    : (draft?.description?.trim().length ?? 0) >= 10 && !!draft?.reported_by_name?.trim()

  function update(key: keyof PublicChatIntakeFields, value: string) {
    setDraft((current) => current ? { ...current, [key]: value || null } : current)
  }

  function send(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim()) return
    void chat.send(message)
    setMessage('')
  }

  if (isReview) {
    return (
      <div className="space-y-4 text-left">
        <div className="rounded border border-emerald-900/40 bg-emerald-950/20 p-3 text-sm text-emerald-100">Review your report before submitting. You can edit every answer.</div>
        {locationLabel && <div className="rounded border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-300"><span className="block text-[10px] uppercase tracking-widest text-zinc-500">Location</span>{locationLabel}</div>}
        {kind === 'intake' && <Field label="Your name"><input value={draft.reported_by_name ?? ''} onChange={(e) => update('reported_by_name', e.target.value)} maxLength={255} className={INPUT} /></Field>}
        <Field label="What happened?"><textarea value={draft.description ?? ''} onChange={(e) => update('description', e.target.value)} rows={6} maxLength={10000} className={INPUT} /></Field>
        <Field label="Date and time" optional><input value={draft.occurred_at_text ?? ''} onChange={(e) => update('occurred_at_text', e.target.value)} maxLength={255} className={INPUT} /></Field>
        {kind === 'report' ? <>
          <Field label="Location" optional><input value={draft.location ?? ''} onChange={(e) => update('location', e.target.value)} maxLength={255} className={INPUT} /></Field>
          <Field label="Names of all involved" optional><textarea value={draft.involved_parties ?? ''} onChange={(e) => update('involved_parties', e.target.value)} rows={2} maxLength={2000} className={INPUT} /></Field>
          <Field label="Contact for follow-up" optional><input value={draft.contact_info ?? ''} onChange={(e) => update('contact_info', e.target.value)} maxLength={255} className={INPUT} /></Field>
        </> : <>
          <Field label="Witnesses" optional><input value={draft.witnesses.map((w) => w.name).join(', ')} onChange={(e) => setDraft((current) => current ? { ...current, witnesses: e.target.value.split(',').map((name) => name.trim()).filter(Boolean).map((name) => ({ name })) } : current)} maxLength={2000} className={INPUT} /></Field>
          <Field label="Suggested next steps" optional><textarea value={draft.corrective_actions ?? ''} onChange={(e) => update('corrective_actions', e.target.value)} rows={3} maxLength={10000} className={INPUT} /></Field>
        </>}
        {reviewExtras}
        <SubmissionDisclaimer />
        {submitError && <p className="text-sm text-red-400">{submitError}</p>}
        <button type="button" onClick={() => onSubmit(draft)} disabled={!requiredComplete || submitting} className="flex w-full items-center justify-center rounded bg-emerald-700 py-2.5 font-medium text-white transition hover:bg-emerald-600 disabled:opacity-50">{submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Submit report'}</button>
        <button type="button" onClick={() => setDraft(null)} className="w-full text-xs text-zinc-500 underline hover:text-zinc-300">Continue chat</button>
      </div>
    )
  }

  return (
    <div className="space-y-4 text-left">
      <div className="text-center"><h1 className="text-lg font-semibold text-zinc-100">Report an incident</h1>{companyName && <p className="mt-1 text-sm text-zinc-400">{companyName}</p>}{locationLabel && <p className="mt-1 text-sm text-zinc-400">Location: {locationLabel}</p>}</div>
      <div className="max-h-[48vh] space-y-2.5 overflow-y-auto rounded border border-zinc-800 bg-zinc-950/40 p-3">
        {chat.messages.map((entry, index) => <div key={index} className={`flex ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}><div className={`max-w-[88%] rounded-xl px-3 py-2 text-sm ${entry.role === 'user' ? 'border border-emerald-500/25 bg-emerald-500/15 text-zinc-100' : 'border border-zinc-800 bg-zinc-900 text-zinc-200'}`}>{entry.content}</div></div>)}
        {chat.sending && <div className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking...</div>}
      </div>
      {chat.error && <div className="space-y-2 text-sm text-amber-300"><p>{chat.error}</p><button type="button" onClick={() => setDraft(chat.fields)} className="underline">Review report</button></div>}
      <form onSubmit={send} className="flex gap-2"><input autoFocus value={message} onChange={(e) => setMessage(e.target.value)} disabled={chat.sending} maxLength={600} placeholder="Type your reply..." className="min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-700 focus:outline-none" /><button type="submit" disabled={!message.trim() || chat.sending} className="flex h-10 w-10 items-center justify-center rounded bg-emerald-700 text-white disabled:opacity-50"><Send className="h-4 w-4" /></button></form>
    </div>
  )
}

function Field({ label, optional, children }: { label: string; optional?: boolean; children: React.ReactNode }) {
  return <label className="block"><span className="text-xs uppercase tracking-wide text-zinc-400">{label}{optional && <span className="ml-1 normal-case tracking-normal text-zinc-600">(optional)</span>}</span>{children}</label>
}
