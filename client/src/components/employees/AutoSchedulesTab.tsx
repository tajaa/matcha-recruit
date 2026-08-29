import { useEffect, useRef, useState } from 'react'
import { CalendarClock, Loader2, Play, Save, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  fetchAutoSchedule, fetchWeekTemplates, runAutoScheduleNow, saveAutoSchedule,
} from '../../api/employees/employeeSchedule'
import type {
  ScheduleAutomationCadence, ScheduleAutomationRule, WeekTemplate,
} from '../../types/employeeSchedule'
import { addDays, errorMessage, startOfWeekSunday, toISODate, WEEKDAY_LABELS } from '../../types/employeeSchedule'
import { useToast } from '../ui'


const inputCls = 'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none'

type FormState = {
  enabled: boolean
  cadence: ScheduleAutomationCadence
  weekTemplateId: string
  runWeekday: number
  runDate: string
  runTime: string
  targetWeeksAhead: number
  targetWeekStart: string
}

function defaults(): FormState {
  const tomorrow = addDays(toISODate(new Date()), 1)
  const nextSunday = addDays(toISODate(startOfWeekSunday(new Date())), 7)
  return {
    enabled: true,
    cadence: 'weekly',
    weekTemplateId: '',
    runWeekday: 4,
    runDate: tomorrow,
    runTime: '09:00',
    targetWeeksAhead: 1,
    targetWeekStart: nextSunday,
  }
}

function fromRule(rule: ScheduleAutomationRule): FormState {
  const fallback = defaults()
  return {
    enabled: rule.enabled,
    cadence: rule.cadence,
    weekTemplateId: rule.week_template_id ?? '',
    runWeekday: rule.run_weekday ?? fallback.runWeekday,
    runDate: rule.run_date ?? fallback.runDate,
    runTime: rule.run_time.slice(0, 5),
    targetWeeksAhead: rule.target_weeks_ahead ?? fallback.targetWeeksAhead,
    targetWeekStart: rule.target_week_start ?? fallback.targetWeekStart,
  }
}

function formatTimestamp(value: string, timezoneName: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezoneName,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default function AutoSchedulesTab({ locationId }: { locationId: string }) {
  const { toast } = useToast()
  const locationIdRef = useRef(locationId)
  locationIdRef.current = locationId
  const [form, setForm] = useState<FormState>(defaults)
  const [rule, setRule] = useState<ScheduleAutomationRule | null>(null)
  const [templates, setTemplates] = useState<WeekTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [generatedWeekStart, setGeneratedWeekStart] = useState<string | null>(null)

  useEffect(() => {
    setRule(null)
    setForm(defaults())
    setTemplates([])
    setGeneratedWeekStart(null)
    setRunning(false)
    if (!locationId) return
    setLoading(true)
    Promise.all([fetchAutoSchedule(locationId), fetchWeekTemplates(locationId)])
      .then(([automation, templateResponse]) => {
        setRule(automation.rule)
        setTemplates(templateResponse.week_templates)
        if (automation.rule) setForm(fromRule(automation.rule))
      })
      .catch((err) => toast(errorMessage(err), 'error'))
      .finally(() => setLoading(false))
  }, [locationId, toast])

  async function save() {
    if (!form.weekTemplateId) {
      toast('Choose a saved week template first.', 'error')
      return
    }
    setSaving(true)
    try {
      const saved = await saveAutoSchedule(locationId, {
        enabled: form.enabled,
        cadence: form.cadence,
        week_template_id: form.weekTemplateId,
        run_time: form.runTime,
        run_weekday: form.cadence === 'weekly' ? form.runWeekday : null,
        run_date: form.cadence === 'once' ? form.runDate : null,
        target_weeks_ahead: form.cadence === 'weekly' ? form.targetWeeksAhead : null,
        target_week_start: form.cadence === 'once' ? form.targetWeekStart : null,
      })
      setRule(saved)
      setForm(fromRule(saved))
      toast(saved.enabled ? 'Auto schedule saved and queued.' : 'Auto schedule saved but paused.', 'success')
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally {
      setSaving(false)
    }
  }

  async function runNow() {
    const runLocationId = locationId
    setRunning(true)
    try {
      const result = await runAutoScheduleNow(runLocationId)
      if (locationIdRef.current !== runLocationId) return
      toast(result.message, result.status === 'generated' ? 'success' : 'info')
      setGeneratedWeekStart(result.status === 'generated' ? result.week_start : null)
      const refreshed = await fetchAutoSchedule(runLocationId)
      if (locationIdRef.current !== runLocationId) return
      setRule(refreshed.rule)
    } catch (err) {
      if (locationIdRef.current === runLocationId) toast(errorMessage(err), 'error')
    } finally {
      if (locationIdRef.current === runLocationId) setRunning(false)
    }
  }

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
              Huume uses this location’s confirmed availability and saved staffing template to prepare a suggestion. It never creates or publishes shifts until a manager approves the proposal in the full shift editor.
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

          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-zinc-400">Week template</span>
            <select aria-label="Week template" className={inputCls} value={form.weekTemplateId} onChange={(e) => setForm({ ...form, weekTemplateId: e.target.value })}>
              <option value="">Choose a template…</option>
              {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
            </select>
            {templates.length === 0 && <span className="text-xs text-amber-400">Create a week template before enabling automation.</span>}
          </label>

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
            <button onClick={save} disabled={saving || !form.weekTemplateId} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-40">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save auto schedule
            </button>
            {rule && <button onClick={runNow} disabled={running} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:text-zinc-100 disabled:opacity-40">
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Run now
            </button>}
          </div>
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
            <Status label="Last result" value={rule.last_status?.replaceAll('_', ' ') ?? 'Has not run'} />
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
