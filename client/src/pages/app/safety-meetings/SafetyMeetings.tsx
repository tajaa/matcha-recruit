import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HardHat, Plus, Users } from 'lucide-react'
import {
  createSafetyMeeting,
  listSafetyMeetingLocations,
  listSafetyMeetings,
  type LocationOption,
  type SafetyMeetingListItem,
} from '../../../api/safetyMeetings'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function statusLabel(status: SafetyMeetingListItem['status']) {
  if (status === 'signed') return 'Signed'
  if (status === 'review') return 'Needs review'
  return 'Recording'
}

export default function SafetyMeetings() {
  const navigate = useNavigate()
  const [meetings, setMeetings] = useState<SafetyMeetingListItem[]>([])
  const [locations, setLocations] = useState<LocationOption[]>([])
  const [loading, setLoading] = useState(true)
  const [showSetup, setShowSetup] = useState(false)
  const [title, setTitle] = useState('Toolbox Talk')
  const [topic, setTopic] = useState('')
  const [locationId, setLocationId] = useState('')
  const [attendees, setAttendees] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([listSafetyMeetings(), listSafetyMeetingLocations()])
      .then(([meetingResponse, locationResponse]) => {
        setMeetings(meetingResponse.meetings)
        setLocations(locationResponse.locations)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load safety meetings.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const begin = async () => {
    if (!title.trim()) return
    setSaving(true)
    setError('')
    try {
      const meeting = await createSafetyMeeting({
        title: title.trim(),
        topic: topic.trim() || null,
        location_id: locationId || null,
        attendee_names: attendees.split('\n').map((name) => name.trim()).filter(Boolean),
      })
      navigate(`/app/safety-meetings/${meeting.id}/record`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the meeting.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-sm font-semibold uppercase tracking-[0.18em] text-emerald-700">Safety records</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Safety meetings</h1>
          <p className="mt-2 max-w-2xl text-slate-600">Record toolbox talks, turn the conversation into a reviewable record, and sign it before it enters your safety history.</p>
        </div>
        <button className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 py-3 font-semibold text-white shadow-sm transition hover:bg-emerald-800" onClick={() => setShowSetup(true)}>
          <Plus size={18} /> Begin a safety meeting
        </button>
      </div>

      {error && <p className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-semibold text-slate-900">Meeting history</h2></div>
        {loading ? <p className="p-6 text-sm text-slate-500">Loading meetings...</p> : meetings.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <div className="mb-4 rounded-2xl bg-emerald-50 p-4 text-emerald-700"><HardHat size={30} /></div>
            <h3 className="font-semibold text-slate-900">No safety meetings yet</h3>
            <p className="mt-2 max-w-md text-sm text-slate-500">Start a toolbox talk and Matcha will transcribe the conversation as it happens.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {meetings.map((meeting) => (
              <button key={meeting.id} className="flex w-full flex-col gap-3 px-5 py-4 text-left transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between" onClick={() => navigate(`/app/safety-meetings/${meeting.id}${meeting.status === 'recording' ? '/record' : ''}`)}>
                <div>
                  <h3 className="font-semibold text-slate-900">{meeting.title}</h3>
                  <p className="mt-1 text-sm text-slate-500">{dateFormat.format(new Date(meeting.started_at))}{meeting.location_name ? ` · ${meeting.location_name}` : ''}</p>
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <span className="inline-flex items-center gap-1 text-slate-500"><Users size={15} /> {meeting.attendee_count}</span>
                  <span className={`rounded-full px-3 py-1 font-medium ${meeting.status === 'signed' ? 'bg-emerald-100 text-emerald-800' : meeting.status === 'review' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'}`}>{statusLabel(meeting.status)}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {showSetup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <div className="mb-5"><h2 className="text-xl font-semibold text-slate-950">Set up the safety meeting</h2><p className="mt-1 text-sm text-slate-500">Add context so the transcript and summary are easier to review.</p></div>
            <div className="space-y-4">
              <label className="block text-sm font-medium text-slate-700">Meeting title<input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
              <label className="block text-sm font-medium text-slate-700">Planned topic (optional)<input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Fall protection, site housekeeping..." value={topic} onChange={(event) => setTopic(event.target.value)} /></label>
              <label className="block text-sm font-medium text-slate-700">Location (optional)<select className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" value={locationId} onChange={(event) => setLocationId(event.target.value)}><option value="">Select a location</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}{location.city ? ` · ${location.city}` : ''}</option>)}</select></label>
              <label className="block text-sm font-medium text-slate-700">Expected attendees <span className="font-normal text-slate-400">(one per line)</span><textarea className="mt-1 min-h-24 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Jordan Lee\nSam Rivera" value={attendees} onChange={(event) => setAttendees(event.target.value)} /></label>
            </div>
            <div className="mt-6 flex justify-end gap-3"><button className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100" onClick={() => setShowSetup(false)}>Cancel</button><button disabled={saving || !title.trim()} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={begin}>{saving ? 'Starting...' : 'Begin meeting'}</button></div>
          </div>
        </div>
      )}
    </main>
  )
}
