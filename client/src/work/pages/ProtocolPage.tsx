import { useEffect, useState } from 'react'
import { BookOpenCheck, Loader2, X } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useToast, Textarea } from '../../components/ui'
import { canReviewEvents } from '../utils/eventsPermissions'
import { getProtocol, updateProtocol, type EmsProtocol } from '../api/protocol'

const EMPTY_PROTOCOL: EmsProtocol = {
  notify_emails: [],
  notify_all_admins: true,
  incident_definition: '',
  culture_notes: '',
  corrective_actions: '',
  updated_at: null,
}

export default function ProtocolPage() {
  const { me, loading: meLoading } = useMe()
  const { toast } = useToast()
  const canReview = canReviewEvents(me?.work_access)

  const [protocol, setProtocol] = useState<EmsProtocol>(EMPTY_PROTOCOL)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [emailInput, setEmailInput] = useState('')

  useEffect(() => {
    if (!canReview) return
    getProtocol()
      .then(setProtocol)
      .catch(() => toast('Failed to load protocol', 'error'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReview])

  function addEmail() {
    const value = emailInput.trim().replace(/,$/, '')
    if (!value || !value.includes('@')) return
    if (protocol.notify_emails.length >= 20) {
      toast('Up to 20 notify contacts', 'error')
      return
    }
    if (protocol.notify_emails.some((e) => e.toLowerCase() === value.toLowerCase())) {
      setEmailInput('')
      return
    }
    setProtocol((p) => ({ ...p, notify_emails: [...p.notify_emails, value] }))
    setEmailInput('')
  }

  function removeEmail(email: string) {
    setProtocol((p) => ({ ...p, notify_emails: p.notify_emails.filter((e) => e !== email) }))
  }

  async function handleSave() {
    setSaving(true)
    try {
      const saved = await updateProtocol({
        notify_emails: protocol.notify_emails,
        notify_all_admins: protocol.notify_all_admins,
        incident_definition: protocol.incident_definition,
        culture_notes: protocol.culture_notes,
        corrective_actions: protocol.corrective_actions,
      })
      setProtocol(saved)
      toast('Protocol saved', 'success')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to save protocol', 'error')
    } finally {
      setSaving(false)
    }
  }

  // meLoading first: canReviewEvents(undefined) reads as "no permission"
  // before /auth/me resolves, so checking !canReview before meLoading
  // flashed the denial stub on every hard reload. Note `loading` (the
  // protocol fetch) never resolves when !canReview — its effect bails
  // before setLoading(false) — so it must be checked AFTER the denial
  // branch, never combined with it.
  if (meLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 text-w-dim animate-spin" />
      </div>
    )
  }

  if (!canReview) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-w-dim">
        You don't have permission to edit the company protocol.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 text-w-dim animate-spin" />
      </div>
    )
  }

  return (
    <div className="h-[calc(100vh-64px)] overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-start gap-3">
          <BookOpenCheck className="w-6 h-6 text-w-accent shrink-0 mt-0.5" />
          <div>
            <h1 className="text-xl font-semibold text-w-text">Company Protocol</h1>
            <p className="text-sm text-w-dim mt-1">
              How Huume handles events logged in your channels — who gets alerted, and what counts
              as an incident here.
            </p>
          </div>
        </div>

        {/* Notify contacts */}
        <div>
          <h2 className="text-[10px] uppercase tracking-[0.14em] text-w-dim font-medium mb-2">
            Notify contacts
          </h2>
          <div className="flex flex-wrap gap-2 mb-2">
            {protocol.notify_emails.map((email) => (
              <span
                key={email}
                className="inline-flex items-center gap-1.5 rounded-full bg-w-surface2 border border-w-line px-3 py-1 text-xs text-w-text"
              >
                {email}
                <button onClick={() => removeEmail(email)} className="text-w-faint hover:text-w-text">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <input
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault()
                addEmail()
              }
            }}
            onBlur={addEmail}
            placeholder="admin@company.com — press Enter to add"
            className="w-full rounded-lg border border-w-line bg-w-surface2 px-3.5 py-2.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-accent/50 transition-colors"
          />
          <label className="flex items-center gap-2 mt-3 text-sm text-w-text">
            <input
              type="checkbox"
              checked={protocol.notify_all_admins}
              onChange={(e) => setProtocol((p) => ({ ...p, notify_all_admins: e.target.checked }))}
              className="rounded border-w-line"
            />
            Also notify all admins
          </label>
        </div>

        <Textarea
          label="What counts as an incident"
          value={protocol.incident_definition}
          onChange={(e) => setProtocol((p) => ({ ...p, incident_definition: e.target.value }))}
          rows={5}
          placeholder="e.g. Any guest complaint involving a refund, any injury requiring first aid or more, any conduct that made a coworker or guest feel unsafe…"
        />
        <p className="text-xs text-w-faint -mt-4">
          Huume reads this when someone mentions an incident in a channel, and judges the event
          against it.
        </p>

        <Textarea
          label="Culture notes"
          value={protocol.culture_notes}
          onChange={(e) => setProtocol((p) => ({ ...p, culture_notes: e.target.value }))}
          rows={4}
          placeholder="How your company talks about and handles events — tone, escalation habits, expectations."
        />

        <Textarea
          label="Default corrective actions"
          value={protocol.corrective_actions}
          onChange={(e) => setProtocol((p) => ({ ...p, corrective_actions: e.target.value }))}
          rows={4}
          placeholder="Typical follow-ups for common event types."
        />
        <p className="text-xs text-w-faint -mt-4">
          Not read by the AI when judging whether something qualifies — shown to admins on
          promotion.
        </p>

        <div className="pt-2 border-t border-w-line">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-w-accent px-4 py-2 text-sm font-medium text-white hover:bg-w-accent-hi transition-colors disabled:opacity-50 inline-flex items-center gap-2"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
