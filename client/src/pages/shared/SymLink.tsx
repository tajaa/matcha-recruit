import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, KeyRound, Loader2, XCircle } from 'lucide-react'
import { PublicPageShell } from './PublicPageShell'
import { GuidedChat } from '../../components/symlink/GuidedChat'
import { useSymLinkSession } from '../../hooks/symlink/useSymLinkSession'

// Public, unauthenticated sym-link page (/sym/:token). The recipient enters
// the company's weekly passcode, then a guided chat collects every required
// item before an editable review step. Nothing is applied on submit — the
// sender reviews and confirms in /app/symlink.
export default function SymLink() {
  const { token } = useParams<{ token: string }>()
  const s = useSymLinkSession(token)
  const [passcode, setPasscode] = useState('')
  const [honeypot, setHoneypot] = useState('')

  if (s.stage === 'validating') {
    return <PublicPageShell><Loader2 className="mx-auto h-8 w-8 animate-spin text-emerald-500" /><p className="mt-4 text-sm text-zinc-400">Checking your link…</p></PublicPageShell>
  }

  if (s.stage === 'invalid') {
    return <PublicPageShell><XCircle className="mx-auto h-12 w-12 text-red-500" /><h1 className="mt-4 text-lg font-semibold text-zinc-100">This link isn&apos;t valid</h1><p className="mt-2 text-sm text-zinc-400">Check the address, or ask the person who sent it for a new one.</p></PublicPageShell>
  }

  if (s.stage === 'closed') {
    return <PublicPageShell><XCircle className="mx-auto h-12 w-12 text-zinc-500" /><h1 className="mt-4 text-lg font-semibold text-zinc-100">{s.info?.closed_message ?? 'This link is closed.'}</h1><p className="mt-2 text-sm text-zinc-400">If you still need to send something, ask the person who sent it for a new link.</p></PublicPageShell>
  }

  if (s.stage === 'submitted') {
    return <PublicPageShell><CheckCircle2 className="mx-auto h-12 w-12 text-emerald-500" /><h1 className="mt-4 text-lg font-semibold text-zinc-100">Sent — thank you</h1><p className="mt-2 text-sm text-zinc-400">{s.info?.company_name ?? 'The sender'} will review what you submitted. You can close this page.</p></PublicPageShell>
  }

  if (s.stage === 'locked') {
    return (
      <PublicPageShell>
        <KeyRound className="mx-auto h-10 w-10 text-emerald-500" />
        <h1 className="mt-4 text-lg font-semibold text-zinc-100">{s.info?.title}</h1>
        {s.info?.company_name && <p className="mt-1 text-sm text-zinc-400">{s.info.company_name}</p>}
        <p className="mt-4 text-sm text-zinc-300">Enter your company&apos;s current passcode to begin. Your manager or the person who sent this link has it.</p>
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); void s.enterPasscode(passcode, honeypot) }}>
          <input autoFocus value={passcode} onChange={(e) => setPasscode(e.target.value)} maxLength={16} placeholder="ABC-234" autoComplete="off" className="w-full rounded border border-zinc-800 bg-zinc-900 px-3 py-3 text-center font-mono text-xl uppercase tracking-[0.3em] text-zinc-100 focus:border-emerald-700 focus:outline-none" />
          <input type="text" name="internal_ref" tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} className="hidden" aria-hidden="true" />
          {s.error && <p className="text-sm text-red-400">{s.error}</p>}
          <button type="submit" disabled={!passcode.trim() || s.sending} className="flex w-full items-center justify-center rounded bg-emerald-700 py-2.5 font-medium text-white hover:bg-emerald-600 disabled:opacity-50">{s.sending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Continue'}</button>
        </form>
      </PublicPageShell>
    )
  }

  if (!s.spec || !s.info) {
    return <PublicPageShell><Loader2 className="mx-auto h-8 w-8 animate-spin text-emerald-500" /></PublicPageShell>
  }

  return (
    <PublicPageShell wide>
      <GuidedChat
        spec={s.spec}
        companyName={s.info.company_name}
        title={s.info.title}
        messages={s.messages}
        fields={s.fields}
        attachments={s.attachments}
        missing={s.missing}
        complete={s.complete}
        sending={s.sending}
        uploading={s.uploading}
        error={s.error}
        mode={s.stage === 'chat' ? 'chat' : 'review'}
        onSend={(text) => void s.send(text)}
        onUpload={(slot, file) => void s.upload(slot, file)}
        onRemoveAttachment={(id) => void s.removeAttachment(id)}
        onReview={() => { s.setError(null); s.setStage('review') }}
        onBackToChat={() => { s.setError(null); s.setStage('chat') }}
        onSubmit={(fields, reviewHoneypot) => void s.submit(fields, reviewHoneypot)}
        submitting={s.stage === 'submitting'}
      />
    </PublicPageShell>
  )
}
