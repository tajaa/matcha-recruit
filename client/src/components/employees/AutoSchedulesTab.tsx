import { useEffect, useRef, useState } from 'react'
import { CalendarClock, Loader2, Play, Save, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  fetchAutoSchedule, fetchWeekTemplates, runAutoScheduleNow, saveAutoSchedule,
} from '../../api/employees/employeeSchedule'
import type {
  ScheduleAutomationCadence, ScheduleAutomationRule, WeekTemplate,
} from '../../types/employeeSchedule'
import { addDays, errorMessage, startOfWeek, toISODate, WEEKDAY_LABELS } from '../../types/employeeSchedule'
import { useToast } from '../ui'
import { useMe } from '../../hooks/useMe'


const inputCls = 'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none'

type FormState = {
  enabled: boolean
  cadence: ScheduleAutomationCadence
  mode: 'template' | 'autopilot'
  weekTemplateId: string
  runWeekday: number
  runDate: string
  runTime: string
  targetWeeksAhead: number
  targetWeekStart: string
}

function defaults(weekStartWeekday = 0): FormState {
  const tomorrow = addDays(toISODate(new Date()), 1)
  // The server rejects a target week that is not aligned to this location's
  // own start day, so the default has to be aligned too.
  const nextWeek = addDays(toISODate(startOfWeek(new Date(), weekStartWeekday)), 7)
  return {
    enabled: true,
    cadence: 'weekly',
    mode: 'template',
    weekTemplateId: '',
    runWeekday: 4,
    runDate: tomorrow,
    runTime: '09:00',
    targetWeeksAhead: 1,
    targetWeekStart: nextWeek,
  }
}

function fromRule(rule: ScheduleAutomationRule, weekStartWeekday = 0): FormState {
  const fallback = defaults(weekStartWeekday)
  return {
    enabled: rule.enabled,
    cadence: rule.cadence,
    mode: rule.mode ?? 'template',
    weekTemplateId: rule.week_template_id ?? '',
    runWeekday: rule.run_weekday ?? fallback.runWeekday,
    runDate: rule.run_date ?? fallback.runDate,
    runTime: rule.run_time.slice(0, 5),
    targetWeeksAhead: rule.target_weeks_ahead ?? fallback.targetWeeksAhead,
    targetWeekStart: rule.target_week_start ?? fallback.targetWeekStart,
  }
}

/** Start of the current week on the LOCATION's wall clock — the same "today"
 * the server's past-week refusal uses. The browser's clock and UTC's both
 * disagree with it for hours around midnight. en-CA formats as YYYY-MM-DD. */
function locationWeekStart(timezoneName: string, weekStartWeekday = 0, now = new Date()): string {
  let today: string
  try {
    today = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezoneName, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(now)
  } catch {
    today = toISODate(now) // unknown zone: UTC, as the server falls back
  }
  return toISODate(startOfWeek(new Date(`${today}T00:00:00Z`), weekStartWeekday))
}

function formatTimestamp(value: string, timezoneName: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezoneName,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default function AutoSchedulesTab({ locationId, weekStartWeekday = 0 }: { locationId: string; weekStartWeekday?: number }) {
  const { toast } = useToast()
  const { hasFeature } = useMe()
  const autopilotEnabled = hasFeature('schedule_autopilot')
  // A new selection is a new request scope, even after returning to the same
  // location. Location identity alone cannot distinguish A → B → A.
  const scopeRequest = useRef(0)
  const saveRequest = useRef(0)
  const runRequest = useRef(0)
  const [form, setForm] = useState<FormState>(defaults)
  const [rule, setRule] = useState<ScheduleAutomationRule | null>(null)
  const [templates, setTemplates] = useState<WeekTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [generatedWeekStart, setGeneratedWeekStart] = useState<string | null>(null)

  // Reset and refetch whenever the location changes — the synchronous
  // setState the rule objects to is clearing the previous location's rule
  // before the request leaves, so it can never render under the new one.
  useEffect(() => {
    const scope = ++scopeRequest.current
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRule(null)
    setForm(defaults(weekStartWeekday))
    setTemplates([])
    setGeneratedWeekStart(null)
    setSaving(false)
    setRunning(false)
    setLoading(!!locationId)
    const current = () => scope === scopeRequest.current
    if (!locationId) return
    Promise.all([fetchAutoSchedule(locationId), fetchWeekTemplates(locationId)])
      .then(([automation, templateResponse]) => {
        if (!current()) return
        setRule(automation.rule)
        setTemplates(templateResponse.week_templates)
        if (automation.rule) setForm(fromRule(automation.rule, weekStartWeekday))
      })
      .catch((err) => { if (current()) toast(errorMessage(err), 'error') })
      .finally(() => { if (current()) setLoading(false) })
    return () => { if (current()) scopeRequest.current += 1 }
  }, [locationId, weekStartWeekday, toast])

  async function save() {
    if (form.mode === 'template' && !form.weekTemplateId) {
      toast('Choose a saved week template first.', 'error')
      return
    }
    const scope = scopeRequest.current
    const request = ++saveRequest.current
    const current = () => scope === scopeRequest.current && request === saveRequest.current
    setSaving(true)
    try {
      const saved = await saveAutoSchedule(locationId, {
        enabled: form.enabled,
        cadence: form.cadence,
        mode: form.mode,
        week_template_id: form.mode === 'template' ? form.weekTemplateId : null,
        run_time: form.runTime,
        run_weekday: form.cadence === 'weekly' ? form.runWeekday : null,
        run_date: form.cadence === 'once' ? form.runDate : null,
        target_weeks_ahead: form.cadence === 'weekly' ? form.targetWeeksAhead : null,
        target_week_start: form.cadence === 'once' ? form.targetWeekStart : null,
      })
      if (!current()) return
      setRule(saved)
      setForm(fromRule(saved, weekStartWeekday))
      toast(saved.enabled ? 'Auto schedule saved.' : 'Auto schedule saved but paused.', 'success')
    } catch (err) {
      if (current()) toast(errorMessage(err), 'error')
    } finally {
      if (current()) setSaving(false)
    }
  }

  async function runNow() {
    const runLocationId = locationId
    const scope = scopeRequest.current
    const request = ++runRequest.current
    const current = () => scope === scopeRequest.current && request === runRequest.current
    setRunning(true)
    try {
      const result = await runAutoScheduleNow(runLocationId)
      if (!current()) return
      toast(result.message, result.status === 'generated' ? 'success' : 'info')
      setGeneratedWeekStart(result.status === 'generated' ? result.week_start : null)
      const refreshed = await fetchAutoSchedule(runLocationId)
      if (!current()) return
      setRule(refreshed.rule)
    } catch (err) {
      if (current()) toast(errorMessage(err), 'error')
    } finally {
      if (current()) setRunning(false)
    }
  }

  // Judged on the SAVED rule, because that is the week Run now builds — an
  // unsaved edit to the field changes nothing until it is saved. ISO dates
  // compare correctly as strings.
  const savedWeekPassed = rule?.cadence === 'once'
    && !!rule.target_week_start
    && rule.target_week_start < locationWeekStart(rule.timezone, weekStartWeekday)

  if (!locationId) {
    return <div className="py-20 text-center text-sm text-zinc-500">Select a location to configure its auto schedule.</div>
  }
  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-4">
        <div className="flex items-start gap-3">
          <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          <div>
            <h2 className="text-sm font-medium text-zinc-100">A ready-to-review week, on your timing</h2>
            <p className="mt-1 text-sm leading-6 text-zinc-400">
              Huume uses this location’s confirmed availability and {form.mode === 'autopilot' ? 'Autopilot forecast' : 'saved staffing template'} to prepare a suggestion. It never creates or publishes shifts until a manager approves the proposal in the full shift editor.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-5 rounded-xl border border-white/[0.07] bg-zinc-900/40 p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-100"><CalendarClock className="h-4 w-4 text-zinc-400" /> Schedule suggestion</h3>
              <p className="mt-1 text-xs text-zinc-500">This setting applies only to the selected location.</p>
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              Enabled
            </label>
          </div>

          {(autopilotEnabled || form.mode === 'autopilot') && (
            <div className="grid grid-cols-2 overflow-hidden rounded-lg border border-emerald-500/25 text-sm">
              <button type="button" onClick={() => setForm({ ...form, mode: 'template' })} className={`px-3 py-2 ${form.mode === 'template' ? 'bg-emerald-500/15 text-emerald-100' : 'text-zinc-500 hover:text-zinc-300'}`}>From template</button>
              <button type="button" disabled={!autopilotEnabled} onClick={() => setForm({ ...form, mode: 'autopilot', weekTemplateId: '' })} className={`px-3 py-2 disabled:opacity-40 ${form.mode === 'autopilot' ? 'bg-emerald-500/15 text-emerald-100' : 'text-zinc-500 hover:text-zinc-300'}`}>Autopilot</button>
            </div>
          )}

          {form.mode === 'autopilot' && !autopilotEnabled && <p className="text-xs leading-5 text-amber-300">Autopilot is no longer enabled. Pause this rule or switch to a saved template.</p>}
          {form.mode === 'template' ? (
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Week template</span>
              <select aria-label="Week template" className={inputCls} value={form.weekTemplateId} onChange={(e) => setForm({ ...form, weekTemplateId: e.target.value })}>
                <option value="">Choose a template…</option>
                {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
              </select>
              {templates.length === 0 && <span className="text-xs text-amber-400">Create a week template before enabling automation.</span>}
            </label>
          ) : (
            <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] px-3 py-2 text-xs leading-5 text-zinc-400">Build from operating hours, committed sales, weather, published schedule history, and the qualified roster.</p>
          )}

          <div className="grid grid-cols-2 overflow-hidden rounded-lg border border-zinc-700 text-sm">
            <button type="button" onClick={() => setForm({ ...form, cadence: 'weekly' })} className={`px-3 py-2 ${form.cadence === 'weekly' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>Every week</button>
            <button type="button" onClick={() => setForm({ ...form, cadence: 'once' })} className={`px-3 py-2 ${form.cadence === 'once' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>One time</button>
          </div>

          {form.cadence === 'weekly' ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Run day">
                <select aria-label="Run day" className={inputCls} value={form.runWeekday} onChange={(e) => setForm({ ...form, runWeekday: Number(e.target.value) })}>
                  {WEEKDAY_LABELS.map((label, index) => <option key={label} value={index}>{label}</option>)}
                </select>
              </Field>
              <Field label="Run time"><input aria-label="Run time" type="time" className={inputCls} value={form.runTime} onChange={(e) => setForm({ ...form, runTime: e.target.value })} /></Field>
              <Field label="Week to prepare">
                <select aria-label="Week to prepare" className={inputCls} value={form.targetWeeksAhead} onChange={(e) => setForm({ ...form, targetWeeksAhead: Number(e.target.value) })}>
                  <option value={1}>Next week</option>
                  <option value={2}>2 weeks ahead</option>
                  <option value={3}>3 weeks ahead</option>
                  <option value={4}>4 weeks ahead</option>
                </select>
              </Field>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Run date"><input aria-label="Run date" type="date" className={inputCls} value={form.runDate} onChange={(e) => setForm({ ...form, runDate: e.target.value })} /></Field>
              <Field label="Run time"><input aria-label="Run time" type="time" className={inputCls} value={form.runTime} onChange={(e) => setForm({ ...form, runTime: e.target.value })} /></Field>
              <Field label="Week starting"><input aria-label="Week starting" type="date" className={inputCls} value={form.targetWeekStart} onChange={(e) => setForm({ ...form, targetWeekStart: e.target.value })} /></Field>
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-t border-white/[0.06] pt-4">
            <button onClick={save} disabled={saving || running || (form.mode === 'template' && !form.weekTemplateId) || (form.mode === 'autopilot' && !autopilotEnabled && form.enabled)} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-40">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save auto schedule
            </button>
            {rule && <button onClick={runNow} disabled={running || saving || (rule.mode === 'autopilot' && !autopilotEnabled)} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:text-zinc-100 disabled:opacity-40">
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Run now
            </button>}
          </div>
          {savedWeekPassed && (
            // A one-time rule's week never moves, so an old rule quietly
            // targets a week that is over — the server refuses Run now on
            // it; say so before the click rather than after.
            <p role="status" className="text-xs text-amber-400">
              The week of {rule.target_week_start} has already passed. Run now will refuse it until you pick a later week and save.
            </p>
          )}
          {generatedWeekStart && (
            <Link
              to={`/ops/schedule/editor?week=${generatedWeekStart}&location=${locationId}`}
              className="inline-flex items-center gap-1.5 text-sm text-emerald-300 hover:text-emerald-200"
            >
              <Sparkles className="h-4 w-4" /> Review the generated week in the full shift editor
            </Link>
          )}
        </div>

        <aside className="space-y-3 rounded-xl border border-white/[0.07] bg-zinc-900/40 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Automation status</h3>
          {!rule ? <p className="text-sm leading-6 text-zinc-500">Not configured for this location yet.</p> : <>
            <Status label="State" value={rule.enabled ? 'Enabled' : 'Paused'} />
            <Status label="Location time zone" value={rule.timezone} />
            <Status label="Next run" value={rule.next_run_at ? formatTimestamp(rule.next_run_at, rule.timezone) : 'Not scheduled'} />
            {/* Stamped with when it ran: the stored result is the LAST attempt's
                and outlives whatever blocked it, so undated it read as a
                current refusal after the week had been cleared. */}
            <Status
              label="Last result"
              value={rule.last_status
                ? `${rule.last_status.replaceAll('_', ' ')}${rule.last_attempt_at ? ` · ${formatTimestamp(rule.last_attempt_at, rule.timezone)}` : ''}`
                : 'Has not run'}
            />
            {rule.last_message && <p className="rounded-lg bg-zinc-950/60 p-3 text-xs leading-5 text-zinc-400">{rule.last_message}</p>}
          </>}
        </aside>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5"><span className="text-xs font-medium text-zinc-400">{label}</span>{children}</label>
}

function Status({ label, value }: { label: string; value: string }) {
  return <div><div className="text-[10px] uppercase tracking-wider text-zinc-600">{label}</div><div className="mt-1 break-words text-sm text-zinc-300">{value}</div></div>
}
