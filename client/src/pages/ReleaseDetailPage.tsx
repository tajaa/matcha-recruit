import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAssignUpc, useRelease, useUpdateRelease } from '../api/hooks'
import { MutationError } from '../components/MutationError'
import { TracksTab } from '../components/TracksTab'
import { displayUpc } from '../lib/format'

export function ReleaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: release, isLoading } = useRelease(id)
  const assignUpc = useAssignUpc()
  const [tab, setTab] = useState<'tracks' | 'metadata'>('tracks')

  if (isLoading || !release) return <div className="p-6">Loading...</div>

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-1">{release.title}</h1>
      <p className="text-sm text-neutral-500 mb-4">
        {release.release_type} - {release.status}
      </p>

      <div className="flex gap-4 border-b mb-4">
        <button
          className={`pb-2 text-sm ${tab === 'tracks' ? 'border-b-2 border-black dark:border-white font-medium' : 'text-neutral-500'}`}
          onClick={() => setTab('tracks')}
        >
          Tracks
        </button>
        <button
          className={`pb-2 text-sm ${tab === 'metadata' ? 'border-b-2 border-black dark:border-white font-medium' : 'text-neutral-500'}`}
          onClick={() => setTab('metadata')}
        >
          Metadata
        </button>
      </div>

      {tab === 'tracks' && <TracksTab releaseId={release.id} />}
      {tab === 'metadata' && (
        <MetadataTab
          release={release}
          onAssignUpc={() => assignUpc.mutate(release.id)}
          assignUpcPending={assignUpc.isPending}
          assignUpcError={assignUpc.error}
        />
      )}
    </div>
  )
}

function MetadataTab({
  release,
  onAssignUpc,
  assignUpcPending,
  assignUpcError,
}: {
  release: { id: string; title: string; catalog_number?: string | null; genre?: string | null; release_date?: string | null; status: string; upc?: string | null }
  onAssignUpc: () => void
  assignUpcPending: boolean
  assignUpcError: unknown
}) {
  const update = useUpdateRelease(release.id)
  const [title, setTitle] = useState(release.title)
  const [catalogNumber, setCatalogNumber] = useState(release.catalog_number ?? '')
  const [genre, setGenre] = useState(release.genre ?? '')
  const [releaseDate, setReleaseDate] = useState(release.release_date ?? '')
  const [status, setStatus] = useState(release.status)

  useEffect(() => {
    setTitle(release.title)
    setCatalogNumber(release.catalog_number ?? '')
    setGenre(release.genre ?? '')
    setReleaseDate(release.release_date ?? '')
    setStatus(release.status)
  }, [release])

  function save(patch: Record<string, unknown>) {
    update.mutate(patch)
  }

  return (
    <div className="text-sm flex flex-col gap-3 max-w-md">
      <div>
        <span className="text-neutral-500 block mb-1">UPC</span>
        {release.upc ? (
          displayUpc(release.upc)
        ) : (
          <button
            className="px-2 py-0.5 rounded border text-xs"
            onClick={onAssignUpc}
            disabled={assignUpcPending}
          >
            Assign UPC
          </button>
        )}
        <MutationError error={assignUpcError} />
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Title</span>
        <input
          className="border rounded px-2 py-1"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title !== release.title && save({ title })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Catalog #</span>
        <input
          className="border rounded px-2 py-1"
          value={catalogNumber}
          onChange={(e) => setCatalogNumber(e.target.value)}
          onBlur={() => catalogNumber !== (release.catalog_number ?? '') && save({ catalog_number: catalogNumber || null })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Genre</span>
        <input
          className="border rounded px-2 py-1"
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
          onBlur={() => genre !== (release.genre ?? '') && save({ genre: genre || null })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Release date</span>
        <input
          type="date"
          className="border rounded px-2 py-1"
          value={releaseDate}
          onChange={(e) => setReleaseDate(e.target.value)}
          onBlur={() => releaseDate !== (release.release_date ?? '') && save({ release_date: releaseDate || null })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Status</span>
        <select
          className="border rounded px-2 py-1"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            save({ status: e.target.value })
          }}
        >
          <option value="draft">Draft</option>
          <option value="ready">Ready</option>
          <option value="packaged">Packaged</option>
          <option value="delivered">Delivered</option>
          <option value="released">Released</option>
        </select>
      </label>

      <MutationError error={update.error} />
    </div>
  )
}
