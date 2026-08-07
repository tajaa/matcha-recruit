import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useArtists, useCreateArtist, useCreateRelease, useReleases } from '../api/hooks'
import { MutationError } from '../components/MutationError'

export function CatalogPage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const { data, isLoading, isError } = useReleases({ q: q || undefined, status: status || undefined })
  const { data: artists } = useArtists()
  const artistNameById = new Map((artists?.items ?? []).map((a) => [a.id, a.name]))
  const createRelease = useCreateRelease()
  const createArtist = useCreateArtist()
  const [showNew, setShowNew] = useState(false)
  const [title, setTitle] = useState('')
  const [artistId, setArtistId] = useState('')
  const [releaseType, setReleaseType] = useState('single')
  const [showNewArtist, setShowNewArtist] = useState(false)
  const [newArtistName, setNewArtistName] = useState('')

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Catalog</h1>
        <button
          className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm"
          onClick={() => setShowNew(true)}
        >
          New release
        </button>
      </div>

      <div className="flex gap-3 mb-4">
        <input
          className="border rounded px-2 py-1 text-sm"
          placeholder="Search title..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="border rounded px-2 py-1 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="ready">Ready</option>
          <option value="packaged">Packaged</option>
          <option value="delivered">Delivered</option>
          <option value="released">Released</option>
        </select>
      </div>

      {showNew && (
        <dialog
          open
          className="rounded-lg border p-4 bg-white dark:bg-neutral-900 dark:text-white w-full max-w-md"
        >
          <h2 className="font-medium mb-3">New release</h2>
          <div className="flex flex-col gap-2">
            <input
              className="border rounded px-2 py-1 text-sm"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            {!showNewArtist ? (
              <div className="flex gap-2">
                <select
                  className="border rounded px-2 py-1 text-sm flex-1"
                  value={artistId}
                  onChange={(e) => setArtistId(e.target.value)}
                >
                  <option value="">Select primary artist...</option>
                  {artists?.items.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <button className="px-2 py-1 rounded border text-xs whitespace-nowrap" onClick={() => setShowNewArtist(true)}>
                  + New artist
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  className="border rounded px-2 py-1 text-sm flex-1"
                  placeholder="Artist name"
                  value={newArtistName}
                  onChange={(e) => setNewArtistName(e.target.value)}
                  autoFocus
                />
                <button
                  className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                  disabled={!newArtistName || createArtist.isPending}
                  onClick={() => {
                    createArtist.mutate(
                      { name: newArtistName },
                      {
                        onSuccess: (artist) => {
                          setArtistId(artist.id)
                          setNewArtistName('')
                          setShowNewArtist(false)
                        },
                      },
                    )
                  }}
                >
                  Create
                </button>
                <button className="px-2 py-1 rounded border text-xs" onClick={() => setShowNewArtist(false)}>
                  Cancel
                </button>
              </div>
            )}
            <MutationError error={createArtist.error} />
            <select
              className="border rounded px-2 py-1 text-sm"
              value={releaseType}
              onChange={(e) => setReleaseType(e.target.value)}
            >
              <option value="single">Single</option>
              <option value="ep">EP</option>
              <option value="album">Album</option>
            </select>
          </div>
          <MutationError error={createRelease.error} />
          <div className="flex gap-2 mt-4 justify-end">
            <button className="px-3 py-1.5 text-sm" onClick={() => setShowNew(false)}>
              Cancel
            </button>
            <button
              className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm disabled:opacity-50"
              disabled={!title || !artistId || createRelease.isPending}
              onClick={() => {
                createRelease.mutate(
                  { title, primary_artist_id: artistId, release_type: releaseType },
                  { onSuccess: () => setShowNew(false) },
                )
              }}
            >
              Create
            </button>
          </div>
        </dialog>
      )}

      {isError ? (
        <p className="text-sm text-red-600">Failed to load releases.</p>
      ) : isLoading ? (
        <p>Loading...</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b">
              <th className="py-2">Title</th>
              <th>Artist</th>
              <th>Type</th>
              <th>Status</th>
              <th>UPC</th>
              <th>Release date</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((release) => (
              <tr key={release.id} className="border-b hover:bg-neutral-50 dark:hover:bg-neutral-900">
                <td className="py-2">
                  <Link className="text-blue-600 dark:text-blue-400 hover:underline" to={`/releases/${release.id}`}>
                    {release.title}
                  </Link>
                </td>
                <td>{artistNameById.get(release.primary_artist_id) ?? '--'}</td>
                <td>{release.release_type}</td>
                <td>
                  <span className="px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-800 text-xs">
                    {release.status}
                  </span>
                </td>
                <td>{release.upc ?? '--'}</td>
                <td>{release.release_date ?? '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
