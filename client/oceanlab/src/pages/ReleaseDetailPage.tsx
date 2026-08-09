import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useArtists, useAssignUpc, useRelease, useUpdateRelease, type Release } from '../api/hooks'
import { MutationError } from '../components/MutationError'
import { TracksTab } from '../components/TracksTab'

export function ReleaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: release, isLoading, isError } = useRelease(id)
  const assignUpc = useAssignUpc()
  const [tab, setTab] = useState<'tracks' | 'metadata'>('tracks')

  if (isError) return <div className="p-6 text-sm text-red-600">Failed to load release.</div>
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
          key={release.id}
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
  release: Release
  onAssignUpc: () => void
  assignUpcPending: boolean
  assignUpcError: unknown
}) {
  const update = useUpdateRelease(release.id)
  const { data: artists } = useArtists()
  const [title, setTitle] = useState(release.title)
  const [catalogNumber, setCatalogNumber] = useState(release.catalog_number ?? '')
  const [genre, setGenre] = useState(release.genre ?? '')
  const [releaseDate, setReleaseDate] = useState(release.release_date ?? '')
  const [originalReleaseDate, setOriginalReleaseDate] = useState(release.original_release_date ?? '')
  const [labelName, setLabelName] = useState(release.label_name ?? '')
  const [cLine, setCLine] = useState(release.c_line ?? '')
  const [pLine, setPLine] = useState(release.p_line ?? '')
  const [subgenre, setSubgenre] = useState(release.subgenre ?? '')
  const [territories, setTerritories] = useState(release.territories ?? '')
  const [notes, setNotes] = useState(release.notes ?? '')

  function save(patch: Record<string, unknown>) {
    update.mutate(patch)
  }

  return (
    <div className="text-sm flex flex-col gap-3 max-w-md">
      <div>
        <span className="text-neutral-500 block mb-1">UPC</span>
        {release.upc ? (
          release.upc
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
        <span className="text-neutral-500">Primary artist</span>
        <select
          className="border rounded px-2 py-1"
          value={release.primary_artist_id}
          onChange={(e) => save({ primary_artist_id: e.target.value })}
        >
          {artists?.items.map((artist) => <option key={artist.id} value={artist.id}>{artist.name}</option>)}
        </select>
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

      {([
        ['label_name', 'Label name', labelName, setLabelName, release.label_name ?? ''],
        ['c_line', 'C-line', cLine, setCLine, release.c_line ?? ''],
        ['p_line', 'P-line', pLine, setPLine, release.p_line ?? ''],
        ['subgenre', 'Subgenre', subgenre, setSubgenre, release.subgenre ?? ''],
        ['territories', 'Territories', territories, setTerritories, release.territories ?? ''],
      ] as const).map(([key, label, value, setter, original]) => (
        <label key={key} className="flex flex-col gap-1">
          <span className="text-neutral-500">{label}</span>
          <input
            className="border rounded px-2 py-1"
            value={value}
            onChange={(e) => setter(e.target.value)}
            onBlur={() => value !== original && save({ [key]: value || null })}
          />
        </label>
      ))}

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Original release date</span>
        <input
          type="date"
          className="border rounded px-2 py-1"
          value={originalReleaseDate}
          onChange={(e) => setOriginalReleaseDate(e.target.value)}
          onBlur={() => originalReleaseDate !== (release.original_release_date ?? '') && save({ original_release_date: originalReleaseDate || null })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-neutral-500">Notes</span>
        <textarea
          className="border rounded px-2 py-1"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== (release.notes ?? '') && save({ notes: notes || null })}
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

      <MutationError error={update.error} />
    </div>
  )
}
