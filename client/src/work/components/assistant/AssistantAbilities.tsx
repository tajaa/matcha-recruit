import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, Lock, X } from 'lucide-react'
import {
  connectGoogleFor, disableAssistantAbility, enableAssistantAbility, listAssistantAbilities,
} from '../../api/matchaWork/assistant'
import type { AssistantAbilities as Abilities, AssistantAbility } from '../../api/matchaWork/assistant'
import { apiErrorText } from '../../utils/apiErrorText'

/**
 * What Espresso may do for this person. Looking things up is always on. An
 * ability that acts (send, invite, book) is switched on here, after the person
 * has read what it does with their data. Nothing is switched on by default.
 */

type Contact = { name: string; phone: string; email: string }

function message(error: unknown): string {
  return apiErrorText(error, 'Something went wrong. Please try again.')
}

function ConsentDialog({
  ability, busy, error, onAccept, onClose,
}: {
  ability: AssistantAbility
  busy: boolean
  error: string | null
  onAccept: (contact: Contact | null) => void
  onClose: () => void
}) {
  const saved = ability.settings.contact
  const [contact, setContact] = useState<Contact>({
    name: saved?.name ?? '', phone: saved?.phone ?? '', email: saved?.email ?? '',
  })
  const needsContact = ability.key === 'reservations'
  const contactReady = !needsContact || (contact.name.trim() !== '' && (contact.phone.trim() !== '' || contact.email.trim() !== ''))
  const field = 'w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-xs text-w-text'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label={ability.disclosure?.title}>
      <div className="w-full max-w-md space-y-3 rounded-2xl border border-w-line bg-w-surface p-4">
        <div className="flex items-start gap-2">
          <p className="flex-1 text-sm font-semibold text-w-text">{ability.disclosure?.title}</p>
          <button type="button" onClick={onClose} aria-label="Close" className="text-w-dim hover:text-w-text"><X size={16} /></button>
        </div>
        <ul className="space-y-2">
          {(ability.disclosure?.body ?? []).map((line) => (
            <li key={line} className="text-xs leading-relaxed text-w-dim">{line}</li>
          ))}
        </ul>
        {needsContact && (
          <div className="space-y-1.5 border-t border-w-line pt-3">
            <p className="text-[11px] font-semibold text-w-text">Book under</p>
            <input className={field} placeholder="Full name" value={contact.name}
              onChange={(e) => setContact({ ...contact, name: e.target.value })} aria-label="Full name" />
            <input className={field} placeholder="Phone" value={contact.phone}
              onChange={(e) => setContact({ ...contact, phone: e.target.value })} aria-label="Phone" />
            <input className={field} placeholder="Email" type="email" value={contact.email}
              onChange={(e) => setContact({ ...contact, email: e.target.value })} aria-label="Email" />
          </div>
        )}
        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-w-line px-3 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2">
            Not now
          </button>
          <button
            type="button"
            disabled={busy || !contactReady}
            onClick={() => onAccept(needsContact ? contact : null)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-xs font-semibold text-w-on-accent hover:opacity-90 disabled:opacity-50"
          >
            {busy && <Loader2 size={12} className="animate-spin" />}
            I understand, switch it on
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AssistantAbilities({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<Abilities | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [consenting, setConsenting] = useState<AssistantAbility | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await listAssistantAbilities())
      setLoadError(null)
    } catch (e) {
      setLoadError(message(e))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // Google's consent finishes in a popup, which says so when it closes.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.data === 'gmail-connected') void load()
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [load])

  async function accept(ability: AssistantAbility, contact: Contact | null) {
    setBusy(ability.key)
    setError(null)
    try {
      await enableAssistantAbility(ability.key, {
        consent_version: ability.disclosure?.version ?? null,
        settings: contact ? { contact } : {},
      })
      setConsenting(null)
      await load()
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(null)
    }
  }

  async function switchOff(ability: AssistantAbility) {
    setBusy(ability.key)
    try {
      await disableAssistantAbility(ability.key)
      await load()
    } catch (e) {
      setLoadError(message(e))
    } finally {
      setBusy(null)
    }
  }

  async function connect(ability: AssistantAbility) {
    setBusy(ability.key)
    try {
      const { auth_url } = await connectGoogleFor(ability.key)
      window.open(auth_url, 'espresso-google', 'popup,width=520,height=680')
    } catch (e) {
      setLoadError(message(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l border-w-line bg-w-surface" aria-label="What Espresso can do">
      <div className="flex items-center gap-2 border-b border-w-line px-4 py-3">
        <p className="flex-1 text-sm font-semibold text-w-text">What Espresso can do</p>
        <button type="button" onClick={onClose} aria-label="Close" className="text-w-dim hover:text-w-text"><X size={16} /></button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {data?.commit_mode === 'dry_run' && (
          <p className="flex gap-1.5 rounded-lg bg-orange-500/10 p-2 text-[11px] text-orange-300">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            Dry run: Espresso shows what it would send or book, and nothing leaves yet.
          </p>
        )}
        {loadError && <p role="alert" className="text-xs text-red-400">{loadError}</p>}
        {!data && !loadError && <Loader2 size={16} className="animate-spin text-w-dim" />}
        {data?.abilities.map((ability) => (
          <div key={ability.key} className="space-y-1.5 rounded-xl border border-w-line p-2.5">
            <div className="flex items-center gap-2">
              <p className="flex-1 text-xs font-semibold text-w-text">{ability.label}</p>
              {ability.always_on ? (
                <span className="text-[10px] text-w-dim">Always on</span>
              ) : ability.enabled ? (
                <button type="button" disabled={busy === ability.key} onClick={() => void switchOff(ability)}
                  className="text-[11px] font-semibold text-w-dim hover:text-red-400 disabled:opacity-50">
                  Switch off
                </button>
              ) : (
                <button type="button" disabled={busy === ability.key} onClick={() => { setError(null); setConsenting(ability) }}
                  className="rounded-lg bg-w-accent px-2.5 py-1 text-[11px] font-semibold text-w-on-accent hover:opacity-90 disabled:opacity-50">
                  {ability.consent_outdated ? 'Review and switch on' : 'Switch on'}
                </button>
              )}
            </div>
            <p className="flex items-center gap-1 text-[11px] text-w-dim">
              {ability.acts ? <><Lock size={10} /> Acts for you, only in this private conversation</> : 'Looks things up'}
            </p>
            {ability.enabled && ability.available && !ability.needs_connection && (
              <p className="flex items-center gap-1 text-[11px] text-emerald-400"><CheckCircle2 size={11} /> Ready</p>
            )}
            {ability.enabled && ability.reason && <p className="text-[11px] text-orange-300">{ability.reason}</p>}
            {ability.enabled && ability.needs_connection && (
              <button type="button" disabled={busy === ability.key} onClick={() => void connect(ability)}
                className="rounded-lg border border-w-line px-2.5 py-1 text-[11px] font-semibold text-w-text hover:bg-w-surface2 disabled:opacity-50">
                {data.google.connected ? 'Reconnect Google' : 'Connect Google'}
              </button>
            )}
          </div>
        ))}
      </div>
      {consenting && (
        <ConsentDialog
          ability={consenting}
          busy={busy === consenting.key}
          error={error}
          onAccept={(contact) => void accept(consenting, contact)}
          onClose={() => setConsenting(null)}
        />
      )}
    </aside>
  )
}
