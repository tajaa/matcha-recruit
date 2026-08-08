import { useState } from 'react'
import {
  useAddTrack,
  useAssignIsrc,
  useDeleteTrack,
  useRecordings,
  useReorderTracks,
  useTracks,
  type Track,
} from '../api/hooks'
import { displayIsrc } from '../lib/format'
import { MutationError } from './MutationError'

export function TracksTab({ releaseId }: { releaseId: string }) {
  const { data: tracks, isLoading, isError } = useTracks(releaseId)
  const { data: recordings } = useRecordings()
  const addTrack = useAddTrack(releaseId)
  const reorderTracks = useReorderTracks(releaseId)
  const deleteTrack = useDeleteTrack(releaseId)
  const assignIsrc = useAssignIsrc()

  const [selectedRecording, setSelectedRecording] = useState('')
  const [discNumber, setDiscNumber] = useState(1)

  if (isError) return <div className="text-sm text-red-600">Failed to load tracks.</div>
  if (isLoading) return <div className="text-sm text-neutral-500">Loading tracks...</div>

  const byDisc = new Map<number, Track[]>()
  for (const t of tracks ?? []) {
    const list = byDisc.get(t.disc_number) ?? []
    list.push(t)
    byDisc.set(t.disc_number, list)
  }
  const discs = [...byDisc.keys()].sort((a, b) => a - b)

  function move(disc: number, trackId: string, direction: -1 | 1) {
    const discTracks = [...(byDisc.get(disc) ?? [])].sort((a, b) => a.position - b.position)
    const idx = discTracks.findIndex((t) => t.id === trackId)
    const swapIdx = idx + direction
    if (idx < 0 || swapIdx < 0 || swapIdx >= discTracks.length) return
    const ids = discTracks.map((t) => t.id)
    ;[ids[idx], ids[swapIdx]] = [ids[swapIdx], ids[idx]]
    reorderTracks.mutate({ disc_number: disc, track_ids: ids })
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {discs.length === 0 && <p className="text-sm text-neutral-500">No tracks yet.</p>}

      {discs.map((disc) => {
        const discTracks = [...(byDisc.get(disc) ?? [])].sort((a, b) => a.position - b.position)
        return (
          <div key={disc}>
            {discs.length > 1 && <h3 className="text-xs font-medium text-neutral-500 mb-2">Disc {disc}</h3>}
            <table className="w-full text-sm border-collapse">
              <tbody>
                {discTracks.map((track, idx) => (
                  <tr key={track.id} className="border-b">
                    <td className="py-1.5 pr-2 w-16 text-neutral-500">{track.position}.</td>
                    <td className="py-1.5 pr-2">
                      {track.recording_title}
                      {track.title_override && (
                        <span className="text-neutral-500"> ({track.title_override})</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2 text-xs text-neutral-500 whitespace-nowrap">
                      {track.recording_isrc ? (
                        displayIsrc(track.recording_isrc)
                      ) : (
                        <button
                          className="px-1.5 py-0.5 rounded border text-xs"
                          disabled={assignIsrc.isPending}
                          onClick={() => assignIsrc.mutate(track.recording_id)}
                        >
                          Assign ISRC
                        </button>
                      )}
                    </td>
                    <td className="py-1.5 pr-1 w-8">
                      <button
                        className="px-1 disabled:opacity-30"
                        disabled={idx === 0 || reorderTracks.isPending}
                        onClick={() => move(disc, track.id, -1)}
                        aria-label="Move up"
                      >
                        ▲
                      </button>
                    </td>
                    <td className="py-1.5 pr-2 w-8">
                      <button
                        className="px-1 disabled:opacity-30"
                        disabled={idx === discTracks.length - 1 || reorderTracks.isPending}
                        onClick={() => move(disc, track.id, 1)}
                        aria-label="Move down"
                      >
                        ▼
                      </button>
                    </td>
                    <td className="py-1.5 w-16 text-right">
                      <button
                        className="text-xs text-red-600"
                        disabled={deleteTrack.isPending}
                        onClick={() => deleteTrack.mutate(track.id)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}

      <MutationError error={reorderTracks.error} />
      <MutationError error={deleteTrack.error} />
      <MutationError error={assignIsrc.error} />

      <div className="border-t pt-4">
        <h3 className="text-xs font-medium text-neutral-500 mb-2">Add track</h3>
        <div className="flex gap-2">
          <select
            className="border rounded px-2 py-1 text-sm flex-1"
            value={selectedRecording}
            onChange={(e) => setSelectedRecording(e.target.value)}
          >
            <option value="">Select recording...</option>
            {recordings?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            className="border rounded px-2 py-1 text-sm w-20"
            value={discNumber}
            onChange={(e) => setDiscNumber(Number(e.target.value) || 1)}
            title="Disc number"
          />
          <button
            className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm disabled:opacity-50"
            disabled={!selectedRecording || addTrack.isPending}
            onClick={() =>
              addTrack.mutate(
                { recording_id: selectedRecording, disc_number: discNumber },
                { onSuccess: () => setSelectedRecording('') },
              )
            }
          >
            Add
          </button>
        </div>
        <MutationError error={addTrack.error} />
      </div>
    </div>
  )
}
