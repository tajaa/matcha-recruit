import { useState, type FormEvent } from 'react'
import { MessageCircleQuestion, CheckCircle2, Loader2, Phone, Mail } from 'lucide-react'
import { api } from '../../../api/client'

type Mode = 'email' | 'phone'

export default function AskExpert() {
  const [topic, setTopic] = useState('')
  const [description, setDescription] = useState('')
  const [mode, setMode] = useState<Mode>('email')
  const [phone, setPhone] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const data = await api.post<{ ok: boolean; message: string }>('/expert-advice/request', {
        topic: topic.trim(),
        description: description.trim(),
        preferred_contact: mode,
        phone: mode === 'phone' ? phone.trim() : undefined,
      })
      setResult({ message: data.message })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Something went wrong'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <div className="max-w-2xl mx-auto py-12">
        <div className="rounded-2xl border border-vsc-border bg-vsc-panel p-10 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-500/10 mb-5">
            <CheckCircle2 className="w-7 h-7 text-emerald-500" />
          </div>
          <h2 className="text-xl font-semibold text-vsc-text mb-2">Submitted</h2>
          <p className="text-sm text-vsc-text/70 leading-relaxed">{result.message}</p>
          <button
            onClick={() => { setResult(null); setTopic(''); setDescription(''); setPhone(''); setMode('email') }}
            className="mt-6 px-5 py-2 text-sm rounded-md bg-vsc-accent hover:opacity-90 text-vsc-bg"
          >
            Ask another question
          </button>
        </div>
      </div>
    )
  }

  const valid = topic.trim().length >= 3 && description.trim().length >= 10 && (mode === 'email' || phone.trim().length >= 7)

  return (
    <div className="max-w-2xl mx-auto py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-vsc-panel border border-vsc-border flex items-center justify-center">
          <MessageCircleQuestion className="w-5 h-5 text-vsc-text/80" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-vsc-text">Ask an Expert</h1>
          <p className="text-sm text-vsc-text/60">Live HR advice — direct line to Matcha's founder.</p>
        </div>
      </div>

      <div className="rounded-xl border border-vsc-border bg-vsc-panel p-6 mb-6">
        <p className="text-sm text-vsc-text/80 leading-relaxed">
          Submit any HR question — discipline situations, leave requests, terminations,
          policy gaps. Aaron responds personally within 1 business day, by email or
          phone (your choice). No bot, no template reply.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label className="block text-xs font-medium text-vsc-text/70 uppercase tracking-wider mb-2">
            Topic
          </label>
          <input
            type="text"
            required
            maxLength={200}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Terminating a manager on PIP"
            className="w-full rounded-md border border-vsc-border bg-vsc-bg px-3 py-2.5 text-sm text-vsc-text outline-none focus:border-vsc-accent"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-vsc-text/70 uppercase tracking-wider mb-2">
            What's going on?
          </label>
          <textarea
            required
            rows={6}
            maxLength={4000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Give as much context as you can — state, headcount, specific dates, what's already been documented."
            className="w-full rounded-md border border-vsc-border bg-vsc-bg px-3 py-2.5 text-sm text-vsc-text outline-none focus:border-vsc-accent resize-none"
          />
          <div className="text-[11px] text-vsc-text/40 mt-1">
            {description.length} / 4000
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-vsc-text/70 uppercase tracking-wider mb-2">
            How should we respond?
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setMode('email')}
              className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm border transition-colors ${
                mode === 'email'
                  ? 'bg-vsc-accent/10 border-vsc-accent text-vsc-text'
                  : 'bg-vsc-bg border-vsc-border text-vsc-text/70 hover:text-vsc-text'
              }`}
            >
              <Mail className="w-4 h-4" />
              Email reply
            </button>
            <button
              type="button"
              onClick={() => setMode('phone')}
              className={`flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm border transition-colors ${
                mode === 'phone'
                  ? 'bg-vsc-accent/10 border-vsc-accent text-vsc-text'
                  : 'bg-vsc-bg border-vsc-border text-vsc-text/70 hover:text-vsc-text'
              }`}
            >
              <Phone className="w-4 h-4" />
              Phone callback
            </button>
          </div>
        </div>

        {mode === 'phone' && (
          <div>
            <label className="block text-xs font-medium text-vsc-text/70 uppercase tracking-wider mb-2">
              Phone number
            </label>
            <input
              type="tel"
              required
              maxLength={50}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              className="w-full rounded-md border border-vsc-border bg-vsc-bg px-3 py-2.5 text-sm text-vsc-text outline-none focus:border-vsc-accent"
            />
          </div>
        )}

        {error && <p className="text-sm text-red-500">{error}</p>}

        <button
          type="submit"
          disabled={!valid || submitting}
          className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-vsc-accent hover:opacity-90 text-vsc-bg text-sm font-medium disabled:opacity-50"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          {submitting ? 'Submitting…' : 'Send to Aaron'}
        </button>

        <p className="text-[11px] text-vsc-text/50 text-center">
          One business day response.
        </p>
      </form>
    </div>
  )
}
