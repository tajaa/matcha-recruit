import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, FileText, LockKeyhole, Save } from 'lucide-react'
import { getSafetyMeeting, signSafetyMeeting, updateSafetyMeeting, type ActionItem, type SafetyMeeting } from '../../../api/safetyMeetings'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export default function SafetyMeetingDetail() {
  const { meetingId = '' } = useParams()
  const navigate = useNavigate()
  const [meeting, setMeeting] = useState<SafetyMeeting | null>(null)
  const [summary, setSummary] = useState('')
  const [notes, setNotes] = useState('')
  const [attendees, setAttendees] = useState('')
  const [topics, setTopics] = useState('')
  const [actionItems, setActionItems] = useState('')
  const [signatureName, setSignatureName] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getSafetyMeeting(meetingId).then((record) => {
      setMeeting(record)
      setSummary(record.summary ?? '')
      setNotes(record.manager_notes ?? '')
      setAttendees(record.attendee_names.join('\n'))
      setTopics(record.topics.join('\n'))
      setActionItems(record.action_items.map((item) => item.owner ? `${item.description} | ${item.owner}` : item.description).join('\n'))
    }).catch((err) => setError(err instanceof Error ? err.message : 'Could not load this meeting.'))
  }, [meetingId])

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const updated = await updateSafetyMeeting(meetingId, {
        summary,
        manager_notes: notes,
        attendee_names: attendees.split('\n').map((item) => item.trim()).filter(Boolean),
        topics: topics.split('\n').map((item) => item.trim()).filter(Boolean),
        action_items: actionItems.split('\n').map((item) => item.trim()).filter(Boolean).map((item): ActionItem => {
          const [description, owner] = item.split('|', 2)
          return { description: description.trim(), owner: owner?.trim() || null }
        }),
      })
      setMeeting(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the review.')
    } finally {
      setSaving(false)
    }
  }

  const sign = async () => {
    if (!confirm || !signatureName.trim()) return
    setSaving(true)
    setError('')
    try {
      const updated = await signSafetyMeeting(meetingId, signatureName.trim())
      setMeeting(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign the record.')
    } finally {
      setSaving(false)
    }
  }

  if (!meeting) return <main className="mx-auto max-w-5xl px-6 py-12"><p className="text-slate-500">{error || 'Loading meeting...'}</p></main>
  const locked = meeting.status === 'signed'

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-700">{locked ? 'Signed safety record' : 'Manager review'}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{meeting.title}</h1><p className="mt-2 text-sm text-slate-500">Recorded {dateFormat.format(new Date(meeting.started_at))}{meeting.location_name ? ` · ${meeting.location_name}` : ''}</p></div>{!locked && <button className="text-sm font-semibold text-slate-600 hover:text-slate-950" onClick={() => navigate('/app/safety-meetings')}>Back to meetings</button>}</div>
      {error && <p className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4"><FileText size={18} className="text-emerald-700" /><h2 className="font-semibold text-slate-900">Meeting record</h2></div><div className="space-y-5 p-5">
          <label className="block text-sm font-medium text-slate-700">AI summary<textarea disabled={locked} className="mt-1 min-h-44 w-full rounded-lg border border-slate-300 px-3 py-2 leading-6 disabled:bg-slate-50" value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
          <label className="block text-sm font-medium text-slate-700">Manager notes<textarea disabled={locked} className="mt-1 min-h-28 w-full rounded-lg border border-slate-300 px-3 py-2 leading-6 disabled:bg-slate-50" placeholder="Add corrections, context, or follow-up notes..." value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium text-slate-700">Attendees <span className="font-normal text-slate-400">(one per line)</span><textarea disabled={locked} className="mt-1 min-h-28 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" value={attendees} onChange={(event) => setAttendees(event.target.value)} /></label><label className="block text-sm font-medium text-slate-700">Topics covered <span className="font-normal text-slate-400">(one per line)</span><textarea disabled={locked} className="mt-1 min-h-28 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" value={topics} onChange={(event) => setTopics(event.target.value)} /></label></div>
          <label className="block text-sm font-medium text-slate-700">Action items <span className="font-normal text-slate-400">(one per line; optional owner after |)</span><textarea disabled={locked} className="mt-1 min-h-28 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" placeholder="Inspect the west stairwell | Jordan Lee" value={actionItems} onChange={(event) => setActionItems(event.target.value)} /></label>
          {!locked && <button disabled={saving} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50" onClick={save}><Save size={16} /> {saving ? 'Saving...' : 'Save review edits'}</button>}
        </div></section>

        <aside className="space-y-6"><section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-200 px-5 py-4"><h2 className="font-semibold text-slate-900">Transcript</h2></div><div className="max-h-[28rem] space-y-3 overflow-auto p-5">{meeting.transcript_segments.filter((segment) => segment.text).map((segment) => <p key={segment.idx} className="text-sm leading-6 text-slate-600">{segment.text}</p>)}</div></section>{locked ? <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div className="flex items-center gap-2 font-semibold text-emerald-900"><LockKeyhole size={18} /> Record signed</div><p className="mt-3 text-sm text-emerald-800">Confirmed by <strong>{meeting.signature_name}</strong> on {meeting.signed_at ? dateFormat.format(new Date(meeting.signed_at)) : ' this date'}.</p></section> : <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h2 className="font-semibold text-amber-950">Confirm and sign</h2><p className="mt-2 text-sm leading-6 text-amber-900">Review the transcript and summary. Your typed name and timestamp will be attached to this record, and signing will lock it.</p><label className="mt-4 flex items-start gap-2 text-sm text-amber-950"><input type="checkbox" className="mt-1" checked={confirm} onChange={(event) => setConfirm(event.target.checked)} /> I confirm this record is accurate to the best of my knowledge.</label><input className="mt-4 w-full rounded-lg border border-amber-300 bg-white px-3 py-2" placeholder="Type your full name" value={signatureName} onChange={(event) => setSignatureName(event.target.value)} /><button disabled={saving || !confirm || !signatureName.trim()} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50" onClick={sign}><CheckCircle2 size={17} /> {saving ? 'Signing...' : 'Sign and confirm record'}</button></section>}</aside>
      </div>
    </main>
  )
}
