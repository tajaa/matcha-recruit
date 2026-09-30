import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronRight, FolderPlus, HardDrive, Loader2, Search, Users, X } from 'lucide-react'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import {
  createDriveFolder,
  deleteDriveFile,
  getDriveDownloadUrl,
  getDriveFolder,
  getDriveTree,
  searchDrive,
  updateDriveFile,
  uploadDriveFile,
} from '../api/drive'
import type { DriveFile, DriveFolder, DriveFolderView, DriveSpace, DriveTree } from '../types'
import DriveFolderTree from '../components/panels/drive/DriveFolderTree'
import DriveFileList from '../components/panels/drive/DriveFileList'
import DriveUploadDropzone from '../components/panels/drive/DriveUploadDropzone'
import DriveGrantsDialog from '../components/panels/drive/DriveGrantsDialog'
import DriveMoveDialog from '../components/panels/drive/DriveMoveDialog'
import { DRIVE_MAX_BYTES, hasCap, spaceEntry } from '../components/panels/drive/driveTree'

const SPACE_LABEL: Record<DriveSpace, string> = { general: 'Company', hr: 'HR' }

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

export default function Drive() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { folderId } = useParams<{ folderId?: string }>()
  const [tree, setTree] = useState<DriveTree | null>(null)
  const [view, setView] = useState<DriveFolderView | null>(null)
  const [failedFolder, setFailedFolder] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  // Keyed by the folder it was opened in, so navigating away drops it.
  const [newFolder, setNewFolder] = useState<{ at: string; name: string } | null>(null)
  const [sharing, setSharing] = useState<DriveFolder | null>(null)
  const [moving, setMoving] = useState<DriveFile | null>(null)
  const [query, setQuery] = useState('')
  // Tagged with the query it answers; a late response for an old query is
  // simply never shown.
  const [search, setSearch] = useState<{ q: string; results: DriveFile[] } | null>(null)

  const go = useCallback((id: string) => navigate(`${base}/drive/${id}`), [navigate, base])

  const loadTree = useCallback(() => getDriveTree().then(
    (t) => { setTree(t); return t },
    (err) => { setError(errorText(err, 'Could not load Drive')); return null },
  ), [])

  const loadFolder = useCallback((id: string) => getDriveFolder(id).then(
    (v) => { setView(v); setFailedFolder(null); setError(null) },
    (err) => { setFailedFolder(id); setError(errorText(err, 'Could not open that folder')) },
  ), [])

  useEffect(() => {
    void loadTree().then((t) => {
      if (!t || folderId) return
      const entry = spaceEntry(t, 'general') ?? spaceEntry(t, 'hr')
      if (entry) navigate(`${base}/drive/${entry}`, { replace: true })
    })
    // Initial load only; folder changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (folderId) void loadFolder(folderId)
  }, [folderId, loadFolder])

  const q = query.trim()
  useEffect(() => {
    if (q.length < 2) return
    const timer = window.setTimeout(() => {
      searchDrive(q)
        .then((res) => setSearch({ q, results: res.results }))
        .catch(() => setSearch({ q, results: [] }))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [q])
  const results = q.length >= 2 && search?.q === q ? search.results : null

  const loading = folderId
    ? view?.folder.id !== folderId && failedFolder !== folderId
    : tree === null && !error
  const creating = newFolder !== null && newFolder.at === view?.folder.id ? newFolder : null

  const space: DriveSpace = view?.folder.space ?? 'general'
  const spaceFolders = useMemo(() => tree?.spaces[space]?.folders ?? [], [tree, space])
  const caps = view?.folder.caps ?? []
  const dropBox = !hasCap(caps, 'list') && hasCap(caps, 'add')

  async function refresh() {
    await Promise.all([loadTree(), folderId ? loadFolder(folderId) : Promise.resolve()])
  }

  async function handleFiles(files: File[]) {
    if (!view) return
    const tooBig = files.filter((f) => f.size > DRIVE_MAX_BYTES)
    const ok = files.filter((f) => f.size <= DRIVE_MAX_BYTES)
    setUploading(true)
    setError(null)
    const failed: string[] = tooBig.map((f) => `${f.name} (over 25 MB)`)
    let sent = 0
    for (const file of ok) {
      try {
        await uploadDriveFile(view.folder.id, file)
        sent += 1
      } catch (err) {
        failed.push(`${file.name} (${errorText(err, 'upload failed')})`)
      }
    }
    setUploading(false)
    if (failed.length) setError(`Not uploaded: ${failed.join(', ')}`)
    if (dropBox) setNotice(sent > 0 ? `Sent ${sent} file${sent === 1 ? '' : 's'} to ${view.folder.name}.` : null)
    else await loadFolder(view.folder.id)
  }

  async function submitFolder(e: FormEvent) {
    e.preventDefault()
    if (!view || !creating?.name.trim()) return
    try {
      await createDriveFolder(view.folder.id, creating.name.trim())
      setNewFolder(null)
      await refresh()
    } catch (err) {
      setError(errorText(err, 'Could not create the folder'))
    }
  }

  async function download(file: DriveFile) {
    try {
      const { url } = await getDriveDownloadUrl(file.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setError(errorText(err, 'Could not download that file'))
    }
  }

  async function rename(file: DriveFile, filename: string) {
    try {
      await updateDriveFile(file.id, { filename })
      if (folderId) await loadFolder(folderId)
    } catch (err) {
      setError(errorText(err, 'Could not rename that file'))
    }
  }

  async function remove(file: DriveFile) {
    if (!window.confirm(`Delete "${file.filename}"?`)) return
    try {
      await deleteDriveFile(file.id)
      if (folderId) await loadFolder(folderId)
    } catch (err) {
      setError(errorText(err, 'Could not delete that file'))
    }
  }

  function switchSpace(next: DriveSpace) {
    if (!tree || next === space) return
    const entry = spaceEntry(tree, next)
    if (entry) go(entry)
  }

  const noAccess = tree && !tree.spaces.general.visible && !tree.spaces.hr.visible

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-w-line p-3 md:flex">
        <div className="mb-3 flex rounded-lg bg-w-surface2/60 p-0.5" role="tablist" aria-label="Drive space">
          {(['general', 'hr'] as DriveSpace[]).filter((s) => tree?.spaces[s]?.visible).map((s) => (
            <button
              key={s}
              role="tab"
              aria-selected={space === s}
              onClick={() => switchSpace(s)}
              className={`flex-1 rounded-md px-2 py-1 text-xs font-medium ${space === s ? 'bg-w-surface text-w-text shadow-sm' : 'text-w-dim hover:text-w-text'}`}
            >
              {SPACE_LABEL[s]}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <DriveFolderTree folders={spaceFolders} selectedId={folderId ?? null} onSelect={go} />
        </div>
      </aside>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-5">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="flex items-center gap-2 text-lg font-semibold text-w-text"><HardDrive size={18} /> Drive</h1>
              {view && !results && view.breadcrumbs.length > 0 && (
                <nav aria-label="Breadcrumb" className="mt-0.5 flex flex-wrap items-center gap-0.5 text-xs text-w-faint">
                  {view.breadcrumbs.map((crumb, i) => (
                    <span key={crumb.id} className="flex items-center gap-0.5">
                      {i > 0 && <ChevronRight size={11} />}
                      <button onClick={() => go(crumb.id)} className="hover:text-w-text">{crumb.name}</button>
                    </span>
                  ))}
                </nav>
              )}
            </div>
            <div className="relative w-full sm:w-64">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-w-faint" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search files"
                aria-label="Search files"
                className="w-full rounded-lg border border-w-line bg-w-surface2/60 py-1.5 pl-8 pr-7 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50"
              />
              {query && (
                <button aria-label="Clear search" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-w-faint hover:text-w-text">
                  <X size={13} />
                </button>
              )}
            </div>
          </header>

          {error && <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}
          {notice && <p role="status" className="rounded-lg border border-w-accent/30 bg-w-accent/10 px-3 py-2 text-sm text-w-text">{notice}</p>}

          {results ? (
            <section aria-label="Search results" className="space-y-2">
              <p className="text-xs text-w-faint">{results.length === 0 ? 'No matching files.' : `${results.length} result${results.length === 1 ? '' : 's'}`}</p>
              {results.length > 0 && (
                <ul className="divide-y divide-w-line rounded-xl border border-w-line bg-w-surface">
                  {results.map((file) => (
                    <li key={file.id} className="flex items-center gap-3 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-w-text">{file.filename}</p>
                        <p className="text-[11px] text-w-faint">{file.space ? SPACE_LABEL[file.space] : ''} · {file.folder_name}</p>
                      </div>
                      <button onClick={() => { setQuery(''); go(file.folder_id) }} className="text-xs text-w-dim hover:text-w-text">Open folder</button>
                      <button onClick={() => void download(file)} className="text-xs font-medium text-w-accent hover:underline">Download</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : loading ? (
            <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-w-faint" /></div>
          ) : noAccess ? (
            <p className="rounded-xl border border-dashed border-w-line px-6 py-10 text-center text-sm text-w-dim">
              You don't have access to any Drive folders yet. Ask a workspace admin to share one with you.
            </p>
          ) : view ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-medium text-w-text">{view.folder.name}</h2>
                <div className="flex items-center gap-2">
                  {hasCap(caps, 'grant') && (
                    <button onClick={() => setSharing(view.folder)} className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1 text-xs text-w-dim hover:text-w-text">
                      <Users size={13} /> Share
                    </button>
                  )}
                  {hasCap(caps, 'manage') && !creating && (
                    <button onClick={() => view && setNewFolder({ at: view.folder.id, name: '' })} className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1 text-xs text-w-dim hover:text-w-text">
                      <FolderPlus size={13} /> New folder
                    </button>
                  )}
                </div>
              </div>

              {creating && (
                <form onSubmit={(e) => void submitFolder(e)} className="flex items-center gap-2">
                  <input
                    autoFocus
                    aria-label="New folder name"
                    value={creating.name}
                    onChange={(e) => setNewFolder({ at: creating.at, name: e.target.value })}
                    onKeyDown={(e) => { if (e.key === 'Escape') setNewFolder(null) }}
                    placeholder="Folder name"
                    className="flex-1 rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text outline-none focus:border-w-accent/50"
                  />
                  <button type="submit" className="rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi">Create</button>
                  <button type="button" onClick={() => setNewFolder(null)} className="text-sm text-w-dim hover:text-w-text">Cancel</button>
                </form>
              )}

              {dropBox ? (
                <div className="space-y-2">
                  <p className="text-sm text-w-dim">You can send files to this folder. Only the people who manage it can see them.</p>
                  <DriveUploadDropzone onFiles={(f) => void handleFiles(f)} busy={uploading} prominent />
                </div>
              ) : (
                <>
                  {hasCap(caps, 'add') && <DriveUploadDropzone onFiles={(f) => void handleFiles(f)} busy={uploading} />}
                  {uploading && <p className="flex items-center gap-2 text-xs text-w-faint"><Loader2 size={12} className="animate-spin" /> Uploading…</p>}
                  <DriveFileList
                    folders={view.folders}
                    files={view.files}
                    caps={caps}
                    onOpenFolder={go}
                    onDownload={(f) => void download(f)}
                    onRename={rename}
                    onMove={setMoving}
                    onDelete={(f) => void remove(f)}
                  />
                </>
              )}
            </>
          ) : null}
        </div>
      </div>

      {sharing && <DriveGrantsDialog folder={sharing} onClose={() => { setSharing(null); void loadTree() }} />}
      {moving && (
        <DriveMoveDialog
          file={moving}
          folders={spaceFolders}
          onClose={() => setMoving(null)}
          onMove={async (target) => {
            await updateDriveFile(moving.id, { folder_id: target })
            if (folderId) await loadFolder(folderId)
          }}
        />
      )}
    </div>
  )
}
