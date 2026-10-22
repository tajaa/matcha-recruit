import { useState } from 'react'
import { Bot, Loader2, Trash2, Users } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeSocialAutoreplyMode, CappeSocialConnection, CappeSocialConnectStart, CappeSocialSettings, CappeSocialTone,
} from '../../../types'
import { normalizeHashtags } from '../../../utils/socialSchedule'

const MODES: { value: CappeSocialAutoreplyMode; label: string; help: string }[] = [
  { value: 'off', label: 'Off', help: 'Comments and messages wait in the inbox for you.' },
  { value: 'review', label: 'Draft replies for me', help: 'Each new one gets a suggested reply. Nothing is sent until you press Send.' },
  { value: 'auto', label: 'Answer simple questions', help: 'Clear questions about products, prices, stock, shipping and hours are answered right away. Complaints, order problems and anything unclear wait for you with a draft.' },
]

const TONES: { value: CappeSocialTone; label: string }[] = [
  { value: 'friendly', label: 'Friendly' },
  { value: 'professional', label: 'Professional' },
  { value: 'playful', label: 'Playful' },
  { value: 'minimal', label: 'Brief' },
]

const STATUS: Record<CappeSocialConnection['status'], string> = {
  connected: 'text-emerald-400',
  expired: 'text-amber-400',
  revoked: 'text-zinc-500',
  error: 'text-red-400',
}

export default function Setup({ siteId, configured, connections, settings, onConnections, onSettings }: {
  siteId: string
  configured: boolean
  connections: CappeSocialConnection[]
  settings: CappeSocialSettings | null
  onConnections: (list: CappeSocialConnection[]) => void
  onSettings: (s: CappeSocialSettings) => void
}) {
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    setConnecting(true)
    setError(null)
    try {
      const res = await cappeApi.post<CappeSocialConnectStart>(`/sites/${siteId}/social/connections/meta/start`)
      window.location.assign(res.authorize_url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t start connecting')
      setConnecting(false)
    }
  }

  async function disconnect(c: CappeSocialConnection) {
    const name = c.handle ? `@${c.handle}` : c.display_name || c.platform
    if (!confirm(`Disconnect ${name}? Posts scheduled for it won’t go out there, and its inbox is cleared.`)) return
    setError(null)
    try {
      await cappeApi.delete(`/sites/${siteId}/social/connections/${c.id}`)
      onConnections(connections.filter((x) => x.id !== c.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t disconnect')
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-100"><Users className="h-4 w-4" /> Accounts</h2>
            <p className="mt-0.5 text-sm text-zinc-400">Connect the Instagram business account and Facebook Page you already use. One sign-in covers both.</p>
          </div>
          {configured && (
            <button type="button" onClick={connect} disabled={connecting}
              className="inline-flex items-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
              {connecting && <Loader2 className="h-4 w-4 animate-spin" />}
              {connections.length ? 'Connect more / reconnect' : 'Connect Instagram & Facebook'}
            </button>
          )}
        </div>
        {!configured && (
          <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-sm text-amber-300">
            Instagram and Facebook aren’t set up on this server yet. You can still write and schedule drafts.
          </p>
        )}
        {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
        {connections.length > 0 && (
          <ul className="mt-4 divide-y divide-zinc-800">
            {connections.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-2.5">
                {c.avatar_url ? <img src={c.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />
                  : <div className="h-8 w-8 rounded-full bg-zinc-800" />}
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-zinc-100"><span className="capitalize">{c.platform}</span>
                    <span className="text-zinc-400"> · {c.handle ? `@${c.handle}` : c.display_name}</span></div>
                  <div className="text-xs">
                    <span className={STATUS[c.status]}>{c.status === 'connected' ? 'Connected' : c.status === 'expired' ? 'Needs reconnecting' : c.status}</span>
                    {c.followers_count != null && <span className="text-zinc-500"> · {c.followers_count.toLocaleString()} followers</span>}
                    {c.last_error && c.status !== 'connected' && <span className="text-zinc-500"> · {c.last_error}</span>}
                  </div>
                </div>
                <button type="button" onClick={() => disconnect(c)} aria-label={`Disconnect ${c.platform}`}
                  className="rounded-lg border border-zinc-700 p-2 text-zinc-500 hover:bg-zinc-800 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Keyed by site, not by the settings: a save hands back new settings, and
          remounting on them would wipe the "Saved" note it just showed. */}
      {settings && <ReplySettings key={siteId} siteId={siteId} settings={settings} onSaved={onSettings} />}
    </div>
  )
}

function ReplySettings({ siteId, settings, onSaved }: {
  siteId: string
  settings: CappeSocialSettings
  onSaved: (s: CappeSocialSettings) => void
}) {
  const [form, setForm] = useState({
    ...settings,
    hashtags: settings.default_hashtags.join(' '),
    words: settings.escalate_words.join(', '),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const locked = !settings.autoreply_available
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => { setForm((f) => ({ ...f, [key]: value })); setSaved(false) }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const out = await cappeApi.put<CappeSocialSettings>(`/sites/${siteId}/social/settings`, {
        autoreply_mode: form.autoreply_mode,
        reply_to_comments: form.reply_to_comments,
        reply_to_messages: form.reply_to_messages,
        tone: form.tone,
        business_facts: form.business_facts,
        signature: form.signature?.trim() || null,
        default_hashtags: normalizeHashtags(form.hashtags),
        max_auto_per_hour: form.max_auto_per_hour,
        escalate_words: form.words.split(',').map((w) => w.trim()).filter(Boolean),
      })
      setSaved(true)
      onSaved(out)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-100"><Bot className="h-4 w-4" /> AI replies</h2>
      <p className="mt-0.5 text-sm text-zinc-400">
        Replies are written from your products, prices and stock, your contact details, and the notes below — never guessed.
        Refunds, complaints, allergies and anything legal always come to you.
      </p>
      {!settings.ai_available && (
        <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-sm text-amber-300">
          AI isn’t available on this server right now; replies stay manual.
        </p>
      )}
      {locked && (
        <p className="mt-3 rounded-lg border border-lime-400/20 bg-lime-400/[0.05] px-3 py-2 text-sm text-lime-200">
          AI replies come with the Business and Creator plans.
        </p>
      )}
      <fieldset className="mt-4 space-y-2" disabled={locked}>
        {MODES.map((m) => (
          <label key={m.value} className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${form.autoreply_mode === m.value
            ? 'border-lime-400/50 bg-lime-400/[0.04]' : 'border-zinc-800'} ${locked && m.value !== 'off' ? 'opacity-50' : ''}`}>
            <input type="radio" name="autoreply" checked={form.autoreply_mode === m.value} onChange={() => set('autoreply_mode', m.value)}
              className="mt-1 accent-lime-400" />
            <span><span className="text-sm font-medium text-zinc-100">{m.label}</span>
              <span className="block text-xs text-zinc-400">{m.help}</span></span>
          </label>
        ))}
      </fieldset>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm text-zinc-300">Voice
          <select value={form.tone} onChange={(e) => set('tone', e.target.value as CappeSocialTone)}
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100">
            {TONES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label className="text-sm text-zinc-300">Sign-off (optional)
          <input value={form.signature ?? ''} onChange={(e) => set('signature', e.target.value)} maxLength={120} placeholder="— the Po Coffee team"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
        </label>
        <label className="text-sm text-zinc-300 sm:col-span-2">What should replies know that isn’t on your site?
          <textarea value={form.business_facts} onChange={(e) => set('business_facts', e.target.value)} rows={4} maxLength={4000}
            placeholder="We ship Monday–Thursday. Returns within 30 days, unopened. Oat milk is free."
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
        </label>
        <label className="text-sm text-zinc-300">Your usual hashtags
          <input value={form.hashtags} onChange={(e) => set('hashtags', e.target.value)} placeholder="#coffee #localroaster"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
        </label>
        <label className="text-sm text-zinc-300">Always send to me when someone mentions
          <input value={form.words} onChange={(e) => set('words', e.target.value)} placeholder="wholesale, catering"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
        </label>
        <div className="flex flex-wrap gap-4 text-sm text-zinc-300 sm:col-span-2">
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.reply_to_comments}
            onChange={(e) => set('reply_to_comments', e.target.checked)} className="accent-lime-400" /> Comments</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.reply_to_messages}
            onChange={(e) => set('reply_to_messages', e.target.checked)} className="accent-lime-400" /> Direct messages</label>
          <label className="flex items-center gap-2">At most
            <input type="number" min={0} max={200} value={form.max_auto_per_hour}
              onChange={(e) => set('max_auto_per_hour', Math.max(0, Math.min(200, Number(e.target.value) || 0)))}
              className="w-20 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100" />
            automatic replies an hour</label>
        </div>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
      <div className="mt-4 flex items-center gap-3">
        <button type="button" onClick={save} disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
        {saved && <span className="text-sm text-emerald-400">Saved</span>}
      </div>
    </section>
  )
}
