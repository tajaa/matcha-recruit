import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import {
  connectGoogleDrive,
  disconnectGoogleDrive,
  getGoogleDriveStatus,
  importFromGoogleDrive,
} from '../../../api/drive'
import type { DriveFile, DriveFolder } from '../../../types'
import DriveDialog from './DriveDialog'

type Status = { connected: boolean; email: string | null }

const GOOGLE_LINK = /^(https?:\/\/)?(docs|drive)\.google\.com\//i

export default function DriveGoogleImportDialog({ folder, onImported, onClose }: {
  folder: DriveFolder
  onImported: (file: DriveFile) => void
  onClose: () => void
}) {
  const [status, setStatus] = useState<Status | null>(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkStatus = useCallback(() => getGoogleDriveStatus().then(
    (s) => setStatus(s),
    () => setStatus({ connected: false, email: null }),
  ), [])

  useEffect(() => {
    void checkStatus()
    function onMessage(e: MessageEvent) {
      if (e.origin !== window.location.origin) return
      if (e.data === 'gdrive-connected') void checkStatus()
      if (e.data === 'gdrive-error') setError("Google couldn't complete the connection. Try again.")
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [checkStatus])

  async function connect() {
    setError(null)
    try {
      const { auth_url } = await connectGoogleDrive()
      if (!window.open(auth_url, 'gdrive-oauth', 'width=600,height=700')) setError('Allow popups to connect Google Drive.')
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not start the Google connection.')
    }
  }

  async function disconnect() {
    await disconnectGoogleDrive().catch(() => undefined)
    setStatus({ connected: false, email: null })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!GOOGLE_LINK.test(url.trim())) {
      setError('Paste a link to a Google Doc, Sheet, Slides deck or Drive file.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      onImported(await importFromGoogleDrive(url.trim(), folder.id))
      onClose()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not import that file.')
      setBusy(false)
    }
  }

  return (
    <DriveDialog title="Import from Google Drive" onClose={onClose} dismissible={!busy}>
      {status === null ? (
        <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-w-faint" /></div>
      ) : !status.connected ? (
        <div className="space-y-3">
          <p className="text-sm text-w-dim">
            Connect your Google account to copy a Doc or Drive file into <span className="text-w-text">{folder.name}</span>.
            Matcha only reads the files you paste a link to.
          </p>
          <button type="button" onClick={() => void connect()} className="rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi">
            Connect Google Drive
          </button>
        </div>
      ) : (
        <form onSubmit={(e) => void submit(e)} className="space-y-3">
          <p className="text-xs text-w-faint">
            Connected as {status.email ?? 'your Google account'} ·{' '}
            <button type="button" onClick={() => void disconnect()} className="hover:text-w-text hover:underline">Disconnect</button>
          </p>
          <input
            autoFocus
            aria-label="Google Drive link"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://docs.google.com/document/d/…"
            className="w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50"
          />
          <p className="text-[11px] text-w-faint">
            Matcha saves a copy into {folder.name}. Later edits in Google won't change it — import again for a new version.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-w-dim hover:text-w-text">Cancel</button>
            <button
              type="submit"
              disabled={busy || !url.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50"
            >
              {busy && <Loader2 size={14} className="animate-spin" />} Import
            </button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
    </DriveDialog>
  )
}
