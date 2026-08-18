import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Mic, Square } from 'lucide-react'
import { finishSafetyMeeting, getSafetyMeeting, uploadSafetyMeetingChunk, type SafetyMeeting } from '../../../api/safetyMeetings'
import { useChunkedVoiceRecorder } from '../../../hooks/useChunkedVoiceRecorder'

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remaining = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remaining}`
}

export default function SafetyMeetingRecord() {
  const { meetingId = '' } = useParams()
  const navigate = useNavigate()
  const [meeting, setMeeting] = useState<SafetyMeeting | null>(null)
  const [segments, setSegments] = useState<Record<number, string>>({})
  const [uploading, setUploading] = useState(0)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState('')
  const pendingRef = useRef<Promise<void>[]>([])

  useEffect(() => {
    getSafetyMeeting(meetingId).then((record) => {
      if (record.status !== 'recording') {
        navigate(`/app/safety-meetings/${meetingId}`, { replace: true })
        return
      }
      setMeeting(record)
      setSegments(Object.fromEntries(record.transcript_segments.map((segment) => [segment.idx, segment.text])))
    }).catch((err) => setError(err instanceof Error ? err.message : 'Could not load this meeting.'))
  }, [meetingId, navigate])

  const onChunk = useCallback((blob: Blob, index: number) => {
    setUploading((count) => count + 1)
    const task = uploadSafetyMeetingChunk(meetingId, blob, index)
      .then((result) => {
        if (result.transcript) setSegments((current) => ({ ...current, [result.idx]: result.transcript ?? '' }))
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'A recording segment could not be uploaded.'))
      .finally(() => setUploading((count) => Math.max(0, count - 1)))
    pendingRef.current.push(task)
  }, [meetingId])

  const recorder = useChunkedVoiceRecorder({
    chunkSeconds: 60,
    maxDurationSeconds: 3600,
    onChunk,
    onMaxDuration: () => setError('The one-hour recording limit was reached. End the meeting to review the record.'),
  })

  const endMeeting = async () => {
    setFinishing(true)
    setError('')
    try {
      await recorder.stop()
      await Promise.all(pendingRef.current)
      await finishSafetyMeeting(meetingId)
      navigate(`/app/safety-meetings/${meetingId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not finish the meeting.')
      setFinishing(false)
    }
  }

  const transcript = Object.entries(segments).sort(([a], [b]) => Number(a) - Number(b)).map(([, text]) => text).filter(Boolean)

  if (!meeting) return <main className="mx-auto max-w-4xl px-6 py-12"><p className="text-slate-500">{error || 'Loading meeting...'}</p></main>

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8 flex flex-col gap-5 rounded-2xl bg-slate-950 p-6 text-white sm:flex-row sm:items-center sm:justify-between">
        <div><p className="text-sm font-medium text-emerald-300">Live safety meeting</p><h1 className="mt-1 text-2xl font-semibold">{meeting.title}</h1>{meeting.topic && <p className="mt-1 text-sm text-slate-300">{meeting.topic}</p>}</div>
        <div className="flex items-center gap-4"><span className="font-mono text-2xl tabular-nums">{formatTime(recorder.elapsedSeconds)}</span>{recorder.status === 'recording' ? <button disabled={finishing} className="inline-flex items-center gap-2 rounded-xl bg-red-500 px-4 py-3 font-semibold text-white hover:bg-red-600 disabled:opacity-50" onClick={endMeeting}><Square size={16} fill="currentColor" /> End meeting</button> : <button className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-semibold text-white hover:bg-emerald-400" onClick={() => { setError(''); void recorder.start() }}><Mic size={17} /> Start microphone</button>}</div>
      </div>

      {error && <p className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {finishing && <p className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">Finishing the meeting and compiling the review draft...</p>}

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div><h2 className="font-semibold text-slate-900">Live transcript</h2><p className="mt-1 text-sm text-slate-500">The transcript updates as each audio segment is processed.</p></div>{uploading > 0 && <span className="text-xs font-medium text-slate-500">Processing {uploading} segment{uploading === 1 ? '' : 's'}...</span>}</div>
        {transcript.length === 0 ? <div className="flex flex-col items-center px-6 py-16 text-center"><Mic className="mb-3 text-emerald-600" size={28} /><p className="font-medium text-slate-800">{recorder.status === 'recording' ? 'Listening...' : 'Start the microphone when everyone is ready.'}</p><p className="mt-1 text-sm text-slate-500">Keep Matcha open while the safety talk is underway.</p></div> : <div className="space-y-4 p-5">{transcript.map((text, index) => <p key={`${index}-${text.slice(0, 12)}`} className="rounded-xl bg-slate-50 p-4 text-sm leading-7 text-slate-700">{text}</p>)}</div>}
      </section>
      <div className="mt-5 flex items-center gap-2 text-xs text-slate-500"><CheckCircle2 size={15} className="text-emerald-600" /> Audio is retained privately with the signed record.</div>
    </main>
  )
}
