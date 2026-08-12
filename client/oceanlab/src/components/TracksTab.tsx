import { useEffect, useState } from 'react'
import {
  useAddTrack,
  useAssignIsrc,
  useArtists,
  useCreateRecording,
  useContributors,
  useDeleteTrack,
  useRecordings,
  useRecordingSplits,
  useRecordingWorks,
  useRecordingCredits,
  useUpdateRecordingCredits,
  useUpdateRecordingSplits,
  useUpdateWorkWriters,
  useWorkWriters,
  useUpdateRecording,
  useUpdateTrack,
  useReorderTracks,
  useTracks,
  type Track,
} from '../api/hooks'
import { displayIsrc } from '../lib/format'
import { uploadWithProgress } from '../lib/upload'
import { MutationError } from './MutationError'

export function TracksTab({ releaseId }: { releaseId: string }) {
  const { data: tracks, isLoading, isError } = useTracks(releaseId)
  const { data: recordings } = useRecordings()
  const { data: artists } = useArtists()
  const { data: contributors } = useContributors()
  const addTrack = useAddTrack(releaseId)
  const reorderTracks = useReorderTracks(releaseId)
  const deleteTrack = useDeleteTrack(releaseId)
  const assignIsrc = useAssignIsrc()
  const createRecording = useCreateRecording()

  const [selectedRecording, setSelectedRecording] = useState('')
  const [discNumber, setDiscNumber] = useState(1)
  const [newRecordingTitle, setNewRecordingTitle] = useState('')
  const [newRecordingArtist, setNewRecordingArtist] = useState('')
  const [audioProgress, setAudioProgress] = useState(0)
  const [audioError, setAudioError] = useState('')
  const { data: splits } = useRecordingSplits(selectedRecording)
  const { data: works } = useRecordingWorks(selectedRecording)
  const { data: credits } = useRecordingCredits(selectedRecording)
  const updateRecording = useUpdateRecording(selectedRecording)
  const updateSplits = useUpdateRecordingSplits(selectedRecording)
  const updateCredits = useUpdateRecordingCredits(selectedRecording)

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
                       <TrackTitleEditor track={track} releaseId={releaseId} />
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

      <div className="border-t pt-4">
        <h3 className="text-xs font-medium text-neutral-500 mb-2">Create recording</h3>
        <div className="flex gap-2">
          <input
            className="border rounded px-2 py-1 text-sm flex-1"
            placeholder="Recording title"
            value={newRecordingTitle}
            onChange={(e) => setNewRecordingTitle(e.target.value)}
          />
          <select
            className="border rounded px-2 py-1 text-sm flex-1"
            value={newRecordingArtist}
            onChange={(e) => setNewRecordingArtist(e.target.value)}
          >
            <option value="">Artist...</option>
            {artists?.items.map((artist) => <option key={artist.id} value={artist.id}>{artist.name}</option>)}
          </select>
          <button
            className="px-3 py-1.5 rounded bg-black text-white dark:bg-white dark:text-black text-sm disabled:opacity-50"
            disabled={!newRecordingTitle.trim() || !newRecordingArtist || createRecording.isPending}
            onClick={() => createRecording.mutate(
              { title: newRecordingTitle.trim(), primary_artist_id: newRecordingArtist },
              {
                onSuccess: (recording) => {
                  setNewRecordingTitle('')
                  setSelectedRecording(recording.id)
                  addTrack.mutate(
                    { recording_id: recording.id, disc_number: discNumber },
                    { onSuccess: () => setSelectedRecording(recording.id) },
                  )
                },
              },
            )}
          >
            Create
          </button>
        </div>
        <MutationError error={createRecording.error} />
      </div>

      {selectedRecording && (splits || works) && (
        <div className="border-t pt-4 text-sm">
          <h3 className="text-xs font-medium text-neutral-500 mb-2">Ownership</h3>
          {splits?.map((split) => (
            <div key={split.id} className="flex gap-2 items-center">
              <span>Master {split.share_pct}%</span>
              {split.auto_created && <span className="rounded border px-1 text-[10px]">auto</span>}
            </div>
          ))}
          {works?.map((work) => (
            <div key={work.id} className="flex gap-2 items-center">
              <span>Work: {work.title}</span>
              {work.auto_created && <span className="rounded border px-1 text-[10px]">auto</span>}
            </div>
          ))}
          <RecordingMetadataEditor
            recordingId={selectedRecording}
            splits={splits ?? []}
            credits={credits ?? []}
            works={works ?? []}
            contributors={contributors?.items ?? []}
            onSaveSplits={(payload) => updateSplits.mutate(payload)}
            onSaveCredits={(payload) => updateCredits.mutate(payload)}
          />
        </div>
      )}
      {selectedRecording && (
        <div className="border-t pt-4 text-sm">
          <h3 className="text-xs font-medium text-neutral-500 mb-2">Master metadata</h3>
          <div className="flex flex-wrap gap-2 items-center">
            <label className="border rounded px-2 py-1 text-xs cursor-pointer">
              Upload WAV/FLAC
              <input
                className="hidden"
                type="file"
                accept="audio/wav,audio/x-wav,audio/flac,.wav,.flac"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  setAudioError('')
                  setAudioProgress(0)
                  try {
                    await uploadWithProgress(`/api/oceanlab/recordings/${selectedRecording}/audio`, file, {}, setAudioProgress)
                  } catch (error) {
                    setAudioError(error instanceof Error ? error.message : 'Master upload failed')
                  }
                }}
              />
            </label>
            <label className="flex gap-1 items-center text-xs"><input type="checkbox" onChange={(e) => updateRecording.mutate({ explicit: e.target.checked })} /> Explicit</label>
            <input className="border rounded px-2 py-1 text-xs w-20" placeholder="lang" maxLength={2} onBlur={(e) => e.target.value && updateRecording.mutate({ language: e.target.value })} />
          </div>
          {audioProgress > 0 && audioProgress < 100 && <p className="text-xs mt-2">Uploading master: {audioProgress}%</p>}
          {audioError && <p className="text-xs text-red-600 mt-2">{audioError} The existing master was kept.</p>}
          <MutationError error={updateRecording.error} />
        </div>
      )}
    </div>
  )
}

function TrackTitleEditor({ track, releaseId }: { track: Track; releaseId: string }) {
  const [value, setValue] = useState(track.title_override ?? '')
  const update = useUpdateTrack(track.id, releaseId)
  return (
    <input
      className="border-0 bg-transparent p-0 text-sm w-full focus:ring-1 focus:ring-black"
      aria-label={`Track ${track.position} title`}
      value={value}
      placeholder={track.recording_title}
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => value !== (track.title_override ?? '') && update.mutate({ title_override: value || null })}
    />
  )
}

function RecordingMetadataEditor({
  recordingId: _recordingId,
  splits,
  credits,
  works,
  contributors,
  onSaveSplits,
  onSaveCredits,
}: {
  recordingId: string
  splits: Array<{ contributor_id: string; role: string | null; share_pct: string }>
  credits: Array<{ contributor_id: string; role: string; credited_as?: string | null; position: number }>
  works: Array<{ id: string; title: string }>
  contributors: Array<{ id: string; name: string }>
  onSaveSplits: (payload: Array<{ contributor_id: string; role?: string | null; share_pct: string }>) => void
  onSaveCredits: (payload: Array<{ contributor_id: string; role: string; credited_as?: string | null; position: number }>) => void
}) {
  const [splitDraft, setSplitDraft] = useState(splits.map((row) => ({ contributor_id: row.contributor_id, role: row.role, share_pct: row.share_pct })))
  const [creditDraft, setCreditDraft] = useState(credits.map((row) => ({ contributor_id: row.contributor_id, role: row.role, credited_as: row.credited_as ?? '', position: row.position })))
  return (
    <div className="mt-4 flex flex-col gap-4">
      <div>
        <h4 className="text-xs font-medium text-neutral-500 mb-2">Master ownership splits</h4>
        {splitDraft.map((row, index) => (
          <div key={`${row.contributor_id}-${index}`} className="flex gap-2 mb-1">
            <select className="border rounded px-1 py-1 text-xs flex-1" value={row.contributor_id} onChange={(e) => setSplitDraft((current) => current.map((item, i) => i === index ? { ...item, contributor_id: e.target.value } : item))}>
              {contributors.map((contributor) => <option key={contributor.id} value={contributor.id}>{contributor.name}</option>)}
            </select>
            <input className="border rounded px-1 py-1 text-xs w-20" type="number" min="0" max="100" step="0.001" value={row.share_pct} onChange={(e) => setSplitDraft((current) => current.map((item, i) => i === index ? { ...item, share_pct: e.target.value } : item))} />
          </div>
        ))}
        <button className="border rounded px-2 py-1 text-xs" onClick={() => onSaveSplits(splitDraft)}>Save splits</button>
      </div>
      <div>
        <h4 className="text-xs font-medium text-neutral-500 mb-2">Credits</h4>
        {creditDraft.map((row, index) => (
          <div key={`${row.contributor_id}-${index}`} className="flex gap-2 mb-1">
            <select className="border rounded px-1 py-1 text-xs flex-1" value={row.contributor_id} onChange={(e) => setCreditDraft((current) => current.map((item, i) => i === index ? { ...item, contributor_id: e.target.value } : item))}>
              {contributors.map((contributor) => <option key={contributor.id} value={contributor.id}>{contributor.name}</option>)}
            </select>
            <select className="border rounded px-1 py-1 text-xs" value={row.role} onChange={(e) => setCreditDraft((current) => current.map((item, i) => i === index ? { ...item, role: e.target.value } : item))}>
              {['producer', 'performer', 'mixer', 'mastering_engineer', 'other'].map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </div>
        ))}
        <button className="border rounded px-2 py-1 text-xs" onClick={() => onSaveCredits(creditDraft)}>Save credits</button>
      </div>
      {works.map((work) => (
        <WriterEditor key={work.id} work={work} contributors={contributors} />
      ))}
    </div>
  )
}

function WriterEditor({
  work,
  contributors,
}: {
  work: { id: string; title: string }
  contributors: Array<{ id: string; name: string }>
}) {
  const { data: writers } = useWorkWriters(work.id)
  const update = useUpdateWorkWriters(work.id)
  const [draft, setDraft] = useState<Array<{ contributor_id: string; role: string; share_pct: string }>>([])
  useEffect(() => {
    if (writers) setDraft(writers.map((writer) => ({ contributor_id: writer.contributor_id, role: writer.role, share_pct: writer.share_pct })))
  }, [writers])
  return (
    <div>
      <h4 className="text-xs font-medium text-neutral-500 mb-2">Writers: {work.title}</h4>
      {draft.map((row, index) => (
        <div key={`${row.contributor_id}-${index}`} className="flex gap-2 mb-1">
          <select className="border rounded px-1 py-1 text-xs flex-1" value={row.contributor_id} onChange={(e) => setDraft((current) => current.map((item, i) => i === index ? { ...item, contributor_id: e.target.value } : item))}>
            {contributors.map((contributor) => <option key={contributor.id} value={contributor.id}>{contributor.name}</option>)}
          </select>
          <input className="border rounded px-1 py-1 text-xs w-20" type="number" min="0" max="100" step="0.001" value={row.share_pct} onChange={(e) => setDraft((current) => current.map((item, i) => i === index ? { ...item, share_pct: e.target.value } : item))} />
        </div>
      ))}
      <button className="border rounded px-2 py-1 text-xs" onClick={() => update.mutate(draft)}>Save writers</button>
    </div>
  )
}
