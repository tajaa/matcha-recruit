/** Hand-editable view of the location's scheduling setup.
 *
 *  Huume writes this profile from its interview; a manager has to be able to
 *  correct it without going back through chat, so every field the interview
 *  can set is editable here. */
import { useCallback, useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { Card, Select, Textarea, useToast } from '../../ui'
import { fetchLocationScheduleProfile, saveLocationScheduleProfile } from '../../../api/employees/locationProfile'
import { fetchWeekTemplates } from '../../../api/employees/employeeSchedule'
import type {
  LocationScheduleProfile, LocationScheduleProfileUpdate, OperatingHours, ScheduleJob, WeekTemplate,
} from '../../../types/employeeSchedule'
import { WEEKDAY_LABELS, WEEK_RULE_LABELS, errorMessage } from '../../../types/employeeSchedule'
import { TemplateForm } from './TemplateForm'

const inputCls = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-500'

const DEFAULT_OPEN = '09:00'
const DEFAULT_CLOSE = '17:00'

/** 'unset' is not "closed": a day nobody has answered for is left out of the
 *  PUT entirely, so a manager who only fixes Tuesday does not accidentally
 *  declare the other six days closed. */
type DayStatus = 'unset' | 'closed' | 'open'
type DayDraft = { status: DayStatus; open: string; close: string }

function hoursToDraft(hours: OperatingHours | undefined): DayDraft[] {
  return WEEKDAY_LABELS.map((_label, day) => {
    if (!hours || !(String(day) in hours)) return { status: 'unset', open: DEFAULT_OPEN, close: DEFAULT_CLOSE }
    const window = hours[String(day)]
    if (!window) return { status: 'closed', open: DEFAULT_OPEN, close: DEFAULT_CLOSE }
    return { status: 'open', open: window.open.slice(0, 5), close: window.close.slice(0, 5) }
  })
}

function draftToHours(draft: DayDraft[]): OperatingHours {
  const hours: OperatingHours = {}
  draft.forEach((day, index) => {
    if (day.status === 'unset') return
    hours[String(index)] = day.status === 'closed' ? null : { open: day.open, close: day.close }
  })
  return hours
}

export default function WeekStartPane(
  { locationId, jobs, onSaved }: {
    locationId: string
    jobs: ScheduleJob[]
    /** Fires after any successful profile write. The editor re-reads its
     *  locations from it: `week_start_weekday` decides how the grid is laid
     *  out and which week_start the assistant session will accept, so a stale
     *  copy leaves the grid a day off and 422s the Ask Huume panel. */
    onSaved?: () => void
  },
) {
  const { toast } = useToast()
  const [profile, setProfile] = useState<LocationScheduleProfile | null>(null)
  const [templates, setTemplates] = useState<WeekTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [weekStartWeekday, setWeekStartWeekday] = useState(0)
  const [days, setDays] = useState<DayDraft[]>(() => hoursToDraft(undefined))
  /** 'unset' is not 'none': the week builder treats an unanswered leader
   *  question as missing setup, so "no lead required" has to be a value the
   *  manager can actually pick. */
  const [leaderRule, setLeaderRule] = useState<'unset' | 'none' | string>('unset')
  const [notes, setNotes] = useState('')
  const [openBuffer, setOpenBuffer] = useState('0')
  const [closeBuffer, setCloseBuffer] = useState('0')

  const applyProfile = useCallback((next: LocationScheduleProfile) => {
    setProfile(next)
    setWeekStartWeekday(next.week_start_weekday)
    setDays(hoursToDraft(next.operating_hours))
    setLeaderRule(next.leader_required === false ? 'none' : (next.leader_job_id ?? 'unset'))
    setNotes(next.notes ?? '')
    setOpenBuffer(String(next.open_buffer_minutes ?? 0))
    setCloseBuffer(String(next.close_buffer_minutes ?? 0))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [profileResult, templateResult] = await Promise.all([
        fetchLocationScheduleProfile(locationId),
        fetchWeekTemplates(locationId),
      ])
      applyProfile(profileResult)
      setTemplates(templateResult.week_templates)
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setLoading(false)
    }
  }, [applyProfile, locationId, toast])

  useEffect(() => { void load() }, [load])

  async function persist(payload: LocationScheduleProfileUpdate, message: string) {
    setSaving(true)
    try {
      applyProfile(await saveLocationScheduleProfile(locationId, payload))
      onSaved?.()
      toast(message, 'success')
    } catch (error) {
      toast(errorMessage(error), 'error')
    } finally {
      setSaving(false)
    }
  }

  function setDay(index: number, patch: Partial<DayDraft>) {
    setDays((current) => current.map((day, position) => position === index ? { ...day, ...patch } : day))
  }

  /** Clamped rather than rejected: the server enforces 0–240 anyway, and a
   *  half-typed number must not blow up the whole save of hours + leader. */
  function bufferValue(raw: string): number {
    const parsed = Number.parseInt(raw, 10)
    if (!Number.isFinite(parsed)) return 0
    return Math.min(240, Math.max(0, parsed))
  }

  async function saveSetup() {
    await persist({
      week_start_weekday: weekStartWeekday,
      operating_hours: draftToHours(days),
      leader_job_id: leaderRule === 'unset' || leaderRule === 'none' ? null : leaderRule,
      leader_required: leaderRule === 'unset' ? null : leaderRule !== 'none',
      notes: notes.trim() || null,
      open_buffer_minutes: bufferValue(openBuffer),
      close_buffer_minutes: bufferValue(closeBuffer),
    }, 'Location scheduling setup saved')
  }

  const defaultTemplate = profile?.default_week_template_id
    ? templates.find((template) => template.id === profile.default_week_template_id)
    : undefined

  if (loading) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-zinc-200">Week setup</h3>
        <p className="mt-1 max-w-2xl text-xs leading-5 text-zinc-500">How this location runs a normal week. Huume fills this in when it interviews you; anything it got wrong you can correct here.</p>
        {profile && !profile.week_rules.established && (
          <p className="mt-2 max-w-2xl rounded-lg border border-amber-500/25 bg-amber-500/[0.08] px-2.5 py-1.5 text-xs text-amber-100">
            Still missing: {profile.week_rules.missing.map((field) => WEEK_RULE_LABELS[field]).join(', ')}. Huume won’t build a week until these are saved.
          </p>
        )}
      </div>

      <Card className="space-y-3 border-zinc-800 bg-zinc-900/40 p-4 shadow-none">
        <div>
          <h4 className="text-xs font-medium text-zinc-300">Week starts on</h4>
          <p className="mt-1 text-xs text-zinc-500">Changing this re-aligns the editor&rsquo;s week — the seven day columns will start on the day you pick.</p>
        </div>
        <Select
          label="First day of the week"
          className="max-w-48"
          options={WEEKDAY_LABELS.map((label, day) => ({ value: String(day), label }))}
          value={String(weekStartWeekday)}
          onChange={(event) => setWeekStartWeekday(Number(event.target.value))}
        />
      </Card>

      <Card className="space-y-3 border-zinc-800 bg-zinc-900/40 p-4 shadow-none">
        <div>
          <h4 className="text-xs font-medium text-zinc-300">Operating hours</h4>
          <p className="mt-1 text-xs text-zinc-500">Days left as &ldquo;Not set&rdquo; are not saved either way, so nobody has to guess whether you are closed or just have not said yet.</p>
        </div>
        <div className="space-y-1.5">
          {days.map((day, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 px-2.5 py-2">
              <span className="w-10 text-xs text-zinc-300">{WEEKDAY_LABELS[index]}</span>
              <div className="flex gap-1">
                <button type="button" aria-pressed={day.status === 'open'} onClick={() => setDay(index, { status: 'open' })} className={`rounded-md border px-2 py-1 text-[11px] ${day.status === 'open' ? 'border-emerald-500 bg-emerald-600 text-white' : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'}`}>Open</button>
                <button type="button" aria-pressed={day.status === 'closed'} onClick={() => setDay(index, { status: 'closed' })} className={`rounded-md border px-2 py-1 text-[11px] ${day.status === 'closed' ? 'border-zinc-500 bg-zinc-700 text-zinc-100' : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'}`}>Closed</button>
              </div>
              <input type="time" aria-label={`${WEEKDAY_LABELS[index]} opening time`} value={day.open} disabled={day.status !== 'open'} onChange={(event) => setDay(index, { open: event.target.value })} className={`${inputCls} w-32 disabled:opacity-40`} />
              <span className="text-xs text-zinc-600">to</span>
              <input type="time" aria-label={`${WEEKDAY_LABELS[index]} closing time`} value={day.close} disabled={day.status !== 'open'} onChange={(event) => setDay(index, { close: event.target.value })} className={`${inputCls} w-32 disabled:opacity-40`} />
              {day.status === 'unset' && <span className="text-[11px] text-zinc-600">Not set</span>}
            </div>
          ))}
        </div>
        <div className="border-t border-zinc-800 pt-3">
          <h4 className="text-xs font-medium text-zinc-300">Prep and close</h4>
          <p className="mt-1 text-xs text-zinc-500">Minutes someone must be on the schedule for before the doors open and after they shut. A week that only staffs the open hours reads as fully covered while nobody is in to set up or lock down.</p>
          <div className="mt-2 flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="w-28">Before open</span>
              <input type="number" min={0} max={240} step={5} aria-label="Minutes of prep before open" value={openBuffer} onChange={(event) => setOpenBuffer(event.target.value)} className={`${inputCls} w-24`} />
              <span className="text-zinc-600">min</span>
            </label>
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="w-28">After close</span>
              <input type="number" min={0} max={240} step={5} aria-label="Minutes of cleanup after close" value={closeBuffer} onChange={(event) => setCloseBuffer(event.target.value)} className={`${inputCls} w-24`} />
              <span className="text-zinc-600">min</span>
            </label>
          </div>
        </div>
      </Card>

      <Card className="space-y-3 border-zinc-800 bg-zinc-900/40 p-4 shadow-none">
        <div>
          <h4 className="text-xs font-medium text-zinc-300">Leader on every shift</h4>
          <p className="mt-1 text-xs text-zinc-500">The job someone must be working for a shift to count as covered by a lead.</p>
        </div>
        <Select
          label="Leader job"
          className="max-w-64"
          options={[
            { value: 'none', label: 'No leader required' },
            ...jobs.map((job) => ({ value: job.id, label: job.name })),
          ]}
          placeholder={jobs.length ? 'Not answered yet' : 'Not answered yet — no jobs at this location'}
          value={leaderRule === 'unset' ? '' : leaderRule}
          onChange={(event) => setLeaderRule(event.target.value || 'unset')}
        />
      </Card>

      <Card className="space-y-3 border-zinc-800 bg-zinc-900/40 p-4 shadow-none">
        <Textarea label="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Anything else about how this location schedules — busy nights, split shifts, who to call first." />
      </Card>

      <button onClick={() => void saveSetup()} disabled={saving} className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save week setup
      </button>

      <Card className="space-y-3 border-zinc-800 bg-zinc-900/40 p-4 shadow-none">
        <div>
          <h4 className="text-xs font-medium text-zinc-300">Staffing pattern</h4>
          <p className="mt-1 text-xs text-zinc-500">
            {defaultTemplate
              ? 'The shifts this location runs in a normal week. Editing these changes what Huume and “generate from template” lay down.'
              : 'This location has no default staffing pattern yet. Describe a normal week once and Huume can build from it.'}
          </p>
        </div>
        <TemplateForm
          key={defaultTemplate?.id ?? 'new'}
          locationId={locationId}
          template={defaultTemplate}
          jobs={jobs}
          submitLabel="Save staffing pattern"
          onDone={async (saved) => {
            const templateResult = await fetchWeekTemplates(locationId).catch(() => null)
            if (templateResult) setTemplates(templateResult.week_templates)
            // A brand-new pattern is only the location's default once the
            // profile points at it, so the two writes have to be paired.
            if (profile && profile.default_week_template_id !== saved.id) {
              await persist({ default_week_template_id: saved.id }, 'Staffing pattern saved as this location’s default')
            } else {
              toast('Staffing pattern saved', 'success')
            }
          }}
        />
      </Card>
    </div>
  )
}
