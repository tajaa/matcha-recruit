import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Copy, KeyRound, RefreshCw } from 'lucide-react'
import { getPasscode, listAnnounceChannels, rotatePasscode, updatePasscodeSettings } from '../../../api/symlink/symlink'
import { useMe } from '../../../hooks/useMe'
import type { AnnounceChannel, Passcode } from '../../../types/symlink'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function SymLinkSettings() {
  const { hasFeature } = useMe()
  const ops = hasFeature('matcha_ops')
  const [passcode, setPasscode] = useState<Passcode | null>(null)
  const [channels, setChannels] = useState<AnnounceChannel[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    getPasscode().then(setPasscode).catch((err) => setError(err instanceof Error ? err.message : 'Could not load the passcode.'))
    if (ops) listAnnounceChannels().then((r) => setChannels(r.channels)).catch(() => setChannels([]))
  }, [ops])

  async function run(action: () => Promise<Passcode>) {
    setBusy(true)
    setError('')
    try {
      setPasscode(await action())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That change failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <Link to="/app/symlink" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> All sym-links</Link>
      <h1 className="text-2xl font-semibold text-slate-950">Sym-link passcode</h1>
      <p className="mt-2 max-w-2xl text-slate-600">Everyone who opens one of your links enters this code first. It proves they belong to your company and rotates weekly. Share it in person, on the wall, or in a channel — never in the same message as a link.</p>

      {error && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <div className="flex items-center gap-3 text-slate-500"><KeyRound size={18} /><span className="text-xs font-semibold uppercase tracking-wide">This week&apos;s code</span></div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="font-mono text-4xl font-semibold tracking-[0.25em] text-slate-950">{passcode?.code ?? '···-···'}</span>
          <button disabled={!passcode} onClick={() => { if (passcode) { void navigator.clipboard?.writeText(passcode.code); setCopied(true); setTimeout(() => setCopied(false), 1500) } }} className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"><Copy size={14} /> {copied ? 'Copied' : 'Copy'}</button>
          <button disabled={busy} onClick={() => { if (window.confirm('Rotate now? Anyone who has not yet opened their link will need the new code. People already mid-task keep working.')) void run(rotatePasscode) }} className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"><RefreshCw size={14} /> Rotate now</button>
        </div>
        <p className="mt-3 text-sm text-slate-500">
          {passcode?.rotated_at ? `Rotated ${dateFormat.format(new Date(passcode.rotated_at))}. ` : ''}
          {passcode?.next_rotation_at ? `Next rotation ${dateFormat.format(new Date(passcode.next_rotation_at))}.` : ''}
        </p>
        {passcode?.announced && <p className="mt-1 text-sm text-emerald-700">Posted to your channel.</p>}
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-semibold text-slate-900">Rotation</h2>
        <label className="mt-3 block text-sm text-slate-700">Rotate every
          <select value={passcode?.rotation_weekday ?? 0} disabled={!passcode || busy} onChange={(e) => void run(() => updatePasscodeSettings({ rotation_weekday: Number(e.target.value) }))} className="ml-2 rounded-lg border border-slate-300 px-3 py-2 text-sm">
            {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
          </select>
          <span className="ml-2 text-slate-500">at 06:00 UTC</span>
        </label>
        <p className="mt-2 text-xs text-slate-500">Automatic rotation runs from the background worker once your admin enables the “Sym-link passcode rotation” scheduler.</p>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-semibold text-slate-900">Announce in a channel</h2>
        {ops ? (
          <>
            <p className="mt-1 text-sm text-slate-600">Each rotation posts the new code as a system message in this channel.</p>
            <select value={passcode?.announce_channel_id ?? ''} disabled={!passcode || busy} onChange={(e) => void run(() => e.target.value ? updatePasscodeSettings({ announce_channel_id: e.target.value }) : updatePasscodeSettings({ clear_announce_channel: true }))} className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
              <option value="">Don&apos;t announce</option>
              {channels.map((c) => <option key={c.id} value={c.id}>#{c.name}</option>)}
            </select>
          </>
        ) : (
          <p className="mt-1 text-sm text-slate-500">Available with Matcha Ops. Until then, share the code yourself.</p>
        )}
      </section>
    </main>
  )
}
