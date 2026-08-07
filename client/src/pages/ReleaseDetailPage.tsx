import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAssignUpc, useRelease } from '../api/hooks'
import { displayIsrc } from '../lib/format'

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
        <div className="text-sm flex flex-col gap-2 max-w-md">
          <div>
            <span className="text-neutral-500">UPC: </span>
            {release.upc ? displayIsrc(release.upc) || release.upc : '--'}
            {!release.upc && (
              <button
                className="ml-2 px-2 py-0.5 rounded border text-xs"
                onClick={() => assignUpc.mutate(release.id)}
                disabled={assignUpc.isPending}
              >
                Assign UPC
              </button>
            )}
          </div>
          <div>
            <span className="text-neutral-500">Catalog #: </span>
            {release.catalog_number ?? '--'}
          </div>
          <div>
            <span className="text-neutral-500">Genre: </span>
            {release.genre ?? '--'}
          </div>
        </div>
      )}
    </div>
  )
}

function TracksTab({ releaseId }: { releaseId: string }) {
  return (
    <div className="text-sm text-neutral-500">
      Track editor for release {releaseId} — add/reorder recordings via{' '}
      <code>POST /api/releases/{'{id}'}/tracks</code> and{' '}
      <code>POST /api/releases/{'{id}'}/tracks/reorder</code>.
    </div>
  )
}
