import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Copy, RefreshCw } from 'lucide-react'
import { getPasscode, listAnnounceChannels, rotatePasscode, updatePasscodeSettings } from '../../../api/symlink/symlink'
import { Button, LABEL, Select } from '../../../components/ui'
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
    <div className="max-w-3xl space-y-6">
      <Link to="/app/symlink" className="inline-flex items-center gap-1 text-xs text-zinc-500 transition-colors hover:text-zinc-300">
        <ArrowLeft className="h-3.5 w-3.5" /> All sym-links
      </Link>

      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Sym-link passcode</h1>
        <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-zinc-500">
          Everyone who opens one of your links enters this code first. It proves they belong to your company and
          rotates weekly. Share it in person, on the wall, or in a channel — never in the same message as a link.
        </p>
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
        <span className={LABEL}>This week&apos;s code</span>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="font-mono text-3xl font-semibold tracking-[0.25em] text-zinc-100">
            {passcode?.code ?? '···-···'}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!passcode}
            onClick={() => {
              if (passcode) {
                void navigator.clipboard?.writeText(passcode.code)
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              }
            }}
          >
            <Copy className="h-3.5 w-3.5" /> {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => {
              if (window.confirm('Rotate now? Anyone who has not yet opened their link will need the new code. People already mid-task keep working.')) {
                void run(rotatePasscode)
              }
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Rotate now
          </Button>
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          {passcode?.rotated_at ? `Rotated ${dateFormat.format(new Date(passcode.rotated_at))}. ` : ''}
          {passcode?.next_rotation_at ? `Next rotation ${dateFormat.format(new Date(passcode.next_rotation_at))}.` : ''}
        </p>
        {passcode?.announced && <p className="mt-1 text-xs text-emerald-400">Posted to your channel.</p>}
      </section>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
        <h2 className="text-sm font-medium text-zinc-100">Rotation</h2>
        <div className="mt-3 max-w-xs">
          <Select
            label="Rotate every"
            value={String(passcode?.rotation_weekday ?? 0)}
            disabled={!passcode || busy}
            onChange={(e) => void run(() => updatePasscodeSettings({ rotation_weekday: Number(e.target.value) }))}
            options={WEEKDAYS.map((d, i) => ({ value: String(i), label: d }))}
          />
        </div>
        <p className="mt-2 text-[11px] text-zinc-500">
          At 06:00 UTC. Automatic rotation runs from the background worker once your admin enables the
          &ldquo;Sym-link passcode rotation&rdquo; scheduler.
        </p>
      </section>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
        <h2 className="text-sm font-medium text-zinc-100">Announce in a channel</h2>
        {ops ? (
          <>
            <p className="mt-1 text-xs text-zinc-500">
              Each rotation posts the new code as a system message in this channel.
            </p>
            <div className="mt-3 max-w-sm">
              <Select
                value={passcode?.announce_channel_id ?? ''}
                disabled={!passcode || busy}
                onChange={(e) => void run(() => e.target.value
                  ? updatePasscodeSettings({ announce_channel_id: e.target.value })
                  : updatePasscodeSettings({ clear_announce_channel: true }))}
                options={[
                  { value: '', label: 'Don’t announce' },
                  ...channels.map((c) => ({ value: c.id, label: `#${c.name}` })),
                ]}
              />
            </div>
          </>
        ) : (
          <p className="mt-1 text-xs text-zinc-500">
            Available with Matcha Ops. Until then, share the code yourself.
          </p>
        )}
      </section>
    </div>
  )
}
