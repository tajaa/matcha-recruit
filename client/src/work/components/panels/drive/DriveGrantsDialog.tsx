import { useCallback, useEffect, useState } from 'react'
import { Loader2, Search, X } from 'lucide-react'
import { listDriveGrants, removeDriveGrant, searchDrivePeople, setDriveGrant } from '../../../api/drive'
import type { DriveFolder, DriveGrant, DriveGrantPermission, DrivePerson } from '../../../types'
import DriveDialog from './DriveDialog'

const GRANT_LABEL: Record<DriveGrantPermission, string> = {
  view: 'Can view',
  upload: 'Can submit files only',
  edit: 'Can edit',
}

const GRANT_HINT: Record<DriveGrantPermission, string> = {
  view: 'Open and download files in this folder and its subfolders.',
  upload: "Drop files in without seeing what's already there — e.g. a GM sending a draft to HR.",
  edit: 'Add, rename, move and delete files and folders.',
}

const PERMISSIONS: DriveGrantPermission[] = ['view', 'upload', 'edit']

const selectClass =
  'rounded-md border border-w-line bg-w-surface2/60 px-2 py-1 text-xs text-w-text outline-none focus:border-w-accent/50'

export default function DriveGrantsDialog({ folder, onClose }: { folder: DriveFolder; onClose: () => void }) {
  const [grants, setGrants] = useState<DriveGrant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<{ q: string; people: DrivePerson[] } | null>(null)
  const [permission, setPermission] = useState<DriveGrantPermission>('view')
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(() => listDriveGrants(folder.id).then(
    (res) => { setGrants(res.grants); setLoading(false) },
    (err) => { setError(err instanceof Error ? err.message : 'Could not load access'); setLoading(false) },
  ), [folder.id])

  useEffect(() => { void refresh() }, [refresh])

  const q = query.trim()
  useEffect(() => {
    if (!q) return
    const timer = window.setTimeout(() => {
      searchDrivePeople(q)
        .then((res) => setFound({ q, people: res.people }))
        .catch(() => setFound({ q, people: [] }))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [q])
  // Only ever show the answer to the query currently typed.
  const results = q && found?.q === q ? found.people : []

  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key)
    setError(null)
    try {
      await action()
      await refresh()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not update access')
    } finally {
      setBusy(null)
    }
  }

  const granted = new Set(grants.map((g) => g.user_id))

  return (
    <DriveDialog title={`Access to "${folder.name}"`} onClose={onClose}>
      <p className="mb-3 text-xs text-w-faint">
        {folder.space === 'hr'
          ? 'The HR space is private to workspace admins. People added here get access to this folder and everything inside it.'
          : 'Everyone in the company can already view the Company space. Add people here to let them do more in this folder.'}
      </p>

      <div className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-w-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Add a person by name or email"
            aria-label="Search people"
            className="w-full rounded-md border border-w-line bg-w-surface2/60 py-1.5 pl-7 pr-2 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50"
          />
        </div>
        <select aria-label="Access level" value={permission} onChange={(e) => setPermission(e.target.value as DriveGrantPermission)} className={selectClass}>
          {PERMISSIONS.map((p) => <option key={p} value={p}>{GRANT_LABEL[p]}</option>)}
        </select>
      </div>
      <p className="-mt-1.5 mb-3 text-[11px] text-w-faint">{GRANT_HINT[permission]}</p>

      {results.length > 0 && (
        <ul className="mb-3 max-h-40 overflow-y-auto rounded-lg border border-w-line">
          {results.map((person) => (
            <li key={person.id}>
              <button
                type="button"
                disabled={granted.has(person.id) || busy !== null}
                onClick={() => void run(person.id, async () => {
                  await setDriveGrant(folder.id, person.id, permission)
                  setQuery('')
                })}
                className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-w-surface2 disabled:opacity-50"
              >
                <span className="min-w-0 truncate text-w-text">{person.name} <span className="text-w-faint">{person.email}</span></span>
                <span className="shrink-0 text-[11px] text-w-faint">{granted.has(person.id) ? 'Has access' : 'Add'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 size={16} className="animate-spin text-w-faint" /></div>
      ) : grants.length === 0 ? (
        <p className="py-3 text-center text-xs text-w-faint">No one has been added to this folder.</p>
      ) : (
        <ul className="divide-y divide-w-line rounded-lg border border-w-line">
          {grants.map((grant) => (
            <li key={grant.user_id} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-w-text">{grant.name}</p>
                <p className="truncate text-[11px] text-w-faint">{grant.email}</p>
              </div>
              <select
                aria-label={`Access for ${grant.name}`}
                value={grant.permission}
                disabled={busy !== null}
                onChange={(e) => void run(grant.user_id, () => setDriveGrant(folder.id, grant.user_id, e.target.value as DriveGrantPermission))}
                className={selectClass}
              >
                {PERMISSIONS.map((p) => <option key={p} value={p}>{GRANT_LABEL[p]}</option>)}
              </select>
              <button
                type="button"
                aria-label={`Remove ${grant.name}`}
                disabled={busy !== null}
                onClick={() => void run(grant.user_id, () => removeDriveGrant(folder.id, grant.user_id))}
                className="rounded-md p-1 text-w-faint hover:text-red-400 disabled:opacity-50"
              >
                {busy === grant.user_id ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
    </DriveDialog>
  )
}
