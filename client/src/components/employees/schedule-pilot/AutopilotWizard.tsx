import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Loader2, RefreshCw, Sparkles, X } from 'lucide-react'
import { fetchLocationScheduleProfile, saveLocationScheduleProfile } from '../../../api/employees/locationProfile'
import type { AutopilotReadiness, LocationScheduleProfile } from '../../../types/employeeSchedule'
import { errorMessage } from '../../../types/employeeSchedule'
import { Modal } from '../../ui'
import AutopilotPolicyFields from './AutopilotPolicyFields'
import { policyDraftFromProfile, policyPayload, type AutopilotPolicyDraft } from './autopilotPolicy'

const STEPS = ['Check setup', 'Tune the plan', 'Generate review'] as const

export default function AutopilotWizard({
  locationId, locationName, weekStart, readiness, readinessLoading, readinessError,
  running, onClose, onRefresh, onOpenWeekSetup, onOpenJobs, onProfileSaved, onGenerate,
}: {
  locationId: string
  locationName: string
  weekStart: string
  readiness: AutopilotReadiness | null
  readinessLoading: boolean
  readinessError: string | null
  running: boolean
  onClose(): void
  onRefresh(): Promise<void>
  onOpenWeekSetup(): void
  onOpenJobs(): void
  onProfileSaved(): void
  onGenerate(): Promise<boolean>
}) {
  const [step, setStep] = useState(0)
  const [profile, setProfile] = useState<LocationScheduleProfile | null>(null)
  const [policy, setPolicy] = useState<AutopilotPolicyDraft | null>(null)
  const [profileLoading, setProfileLoading] = useState(true)
  const [profileAttempt, setProfileAttempt] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [leaveAction, setLeaveAction] = useState<'close' | 'weekSetup' | 'jobs' | null>(null)

  useEffect(() => {
    let active = true
    void fetchLocationScheduleProfile(locationId)
      .then((loaded) => {
        if (!active) return
        setProfile(loaded)
        setPolicy(policyDraftFromProfile(loaded))
      })
      .catch((cause) => { if (active) setError(errorMessage(cause)) })
      .finally(() => { if (active) setProfileLoading(false) })
    return () => { active = false }
  }, [locationId, profileAttempt])

  const quality = readiness?.autopilot
  const ready = readiness?.ready === true && !readinessLoading && !readinessError
  const policyChanged = !!profile && !!policy
    && JSON.stringify(policy) !== JSON.stringify(policyDraftFromProfile(profile))

  function leave(action: 'close' | 'weekSetup' | 'jobs') {
    if (policyChanged) {
      setLeaveAction(action)
      return
    }
    if (action === 'close') onClose()
    else if (action === 'weekSetup') onOpenWeekSetup()
    else onOpenJobs()
  }

  function discardAndLeave() {
    const action = leaveAction
    setLeaveAction(null)
    if (action === 'close') onClose()
    else if (action === 'weekSetup') onOpenWeekSetup()
    else if (action === 'jobs') onOpenJobs()
  }

  async function continueFromPolicy() {
    if (!profile || !policy) return
    setError(null)
    try {
      const payload = policyPayload(policy)
      if (policyChanged) {
        setSaving(true)
        const saved = await saveLocationScheduleProfile(locationId, payload)
        setProfile(saved)
        setPolicy(policyDraftFromProfile(saved))
        onProfileSaved()
      }
      setStep(2)
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  async function generate() {
    setError(null)
    const generated = await onGenerate()
    if (generated) onClose()
    else void onRefresh()
  }

  if (leaveAction) {
    return (
      <Modal open onClose={() => setLeaveAction(null)} title="Discard planning changes?">
        <p className="text-sm leading-6 text-zinc-400">Your Autopilot choices have not been saved. Save them from the planning step, or discard them before leaving.</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => { setLeaveAction(null); setStep(1) }} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-200">Keep editing</button>
          <button type="button" onClick={discardAndLeave} className="rounded-lg bg-zinc-700 px-3 py-2 text-xs text-zinc-100">Discard changes</button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal open onClose={() => leave('close')} bare dismissible={!saving && !running}>
      <section role="dialog" aria-modal="true" aria-labelledby="autopilot-wizard-title" className="mx-3 flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-emerald-500/25 bg-zinc-900 shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-zinc-800 px-5 py-4 sm:px-6">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-400">Schedule Autopilot · Step {step + 1} of 3</p>
            <h2 id="autopilot-wizard-title" className="mt-1 text-xl font-medium text-zinc-100">{STEPS[step]}</h2>
            <p className="mt-1 text-xs text-zinc-400">{locationName || 'This location'} · Week of {weekStart}</p>
          </div>
          <button type="button" onClick={() => leave('close')} disabled={saving || running} aria-label="Close Autopilot wizard" className="rounded p-1 text-zinc-500 hover:text-zinc-100 disabled:opacity-40"><X className="h-4 w-4" /></button>
        </header>
        <ol aria-label="Autopilot steps" className="grid grid-cols-3 gap-2 border-b border-zinc-800 px-5 py-3 sm:px-6">
          {STEPS.map((label, index) => (
            <li key={label} className={`flex items-center gap-2 text-[11px] ${index === step ? 'text-emerald-200' : index < step ? 'text-zinc-300' : 'text-zinc-600'}`} aria-current={index === step ? 'step' : undefined}>
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${index === step ? 'border-emerald-400 bg-emerald-500/15' : index < step ? 'border-emerald-600 bg-emerald-600/20' : 'border-zinc-700'}`}>{index < step ? <Check className="h-3 w-3" /> : index + 1}</span>
              <span>{label}</span>
            </li>
          ))}
        </ol>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 sm:px-6">
          {step === 0 && (
            <>
              <p className="text-sm leading-6 text-zinc-300">Autopilot needs saved operating hours, a leader decision, eligible jobs, confirmed availability, and a location timezone before it can prepare this week.</p>
              {readinessLoading ? (
                <p className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" /> Checking this week…</p>
              ) : readinessError ? (
                <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">Could not check readiness: {readinessError}</p>
              ) : ready ? (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200"><Check className="mr-2 inline h-4 w-4" />The required setup is ready.</div>
              ) : (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                  <p className="text-xs font-medium text-amber-200">Resolve these before generating:</p>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-amber-100/90">
                    {(readiness?.blockers.length ? readiness.blockers : ['Readiness is unavailable. Refresh the check.']).map((blocker, index) => <li key={`${index}-${blocker}`}>{blocker}</li>)}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => leave('weekSetup')} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:border-emerald-500/50">Edit week setup</button>
                <button type="button" onClick={() => leave('jobs')} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:border-emerald-500/50">Edit jobs</button>
                <button type="button" onClick={() => { void onRefresh() }} disabled={readinessLoading} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:border-emerald-500/50 disabled:opacity-40"><RefreshCw className="h-3.5 w-3.5" /> Recheck</button>
              </div>
              <p className="text-xs leading-5 text-zinc-500">If the blocker concerns the location timezone or an employee’s availability, update that record, then return here and recheck. You can inspect the next step even while setup is incomplete.</p>
            </>
          )}
          {step === 1 && (
            <>
              <p className="text-sm leading-6 text-zinc-300">These inputs shape demand, but missing sales, weather, or history will not block a build. Autopilot falls back to the saved coverage floor and explains what it could not use.</p>
              <div className="grid gap-2 sm:grid-cols-4">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"><p className="text-[10px] uppercase tracking-wide text-zinc-500">Sales</p><p className="mt-1 text-sm text-zinc-200">{quality ? `${quality.sales_weeks} weeks · ${quality.sales_confidence} confidence` : 'Checking…'}</p></div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"><p className="text-[10px] uppercase tracking-wide text-zinc-500">Weather</p><p className="mt-1 text-sm text-zinc-200">{quality ? `${quality.weather_days_available} of 7 days` : 'Checking…'}</p></div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"><p className="text-[10px] uppercase tracking-wide text-zinc-500">Past schedules</p><p className="mt-1 text-sm text-zinc-200">{quality ? `${quality.history_weeks} weeks` : 'Checking…'}</p></div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"><p className="text-[10px] uppercase tracking-wide text-zinc-500">Hourly sales</p><p className="mt-1 text-sm text-zinc-200">{quality ? (quality.hourly_sales_days ? `${quality.hourly_sales_days} days` : 'None — POS sync adds it') : 'Checking…'}</p></div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
                <h3 className="text-xs font-medium text-zinc-200">Planning choices</h3>
                <p className="mb-3 mt-1 text-xs leading-5 text-zinc-500">These are your operating targets, not legal limits. Leave optional values blank to use Autopilot defaults.</p>
                {profileLoading ? <p className="flex items-center gap-2 text-xs text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading saved choices…</p>
                  : policy ? <AutopilotPolicyFields value={policy} onChange={setPolicy} />
                    : <div className="space-y-2"><p className="text-xs text-red-200">Saved choices could not be loaded.</p><button type="button" onClick={() => { setError(null); setProfileLoading(true); setProfileAttempt((value) => value + 1) }} className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-200">Retry loading choices</button></div>}
              </div>
              {error && <p role="alert" className="text-xs text-red-200">{error}</p>}
            </>
          )}
          {step === 2 && (
            <>
              <p className="text-sm leading-6 text-zinc-300">Autopilot will prepare a suggested week using this store’s saved setup and the inputs available today.</p>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-xs leading-6 text-zinc-300">
                <p><span className="text-zinc-500">Location:</span> {locationName || 'This location'}</p>
                <p><span className="text-zinc-500">Week:</span> {weekStart}</p>
                <p><span className="text-zinc-500">Coverage floor:</span> {profile?.min_floor_staff ?? 1} staff</p>
                <p><span className="text-zinc-500">Weather:</span> {profile?.weather_sensitivity === 'rain_hurts' ? 'Rain lowers demand' : profile?.weather_sensitivity === 'rain_helps' ? 'Rain raises demand' : 'No weather adjustment'}</p>
                <p><span className="text-zinc-500">Target labor:</span> {profile?.target_labor_pct == null ? 'None — pace learned from past weeks' : `${profile.target_labor_pct}% ceiling`}</p>
                <p><span className="text-zinc-500">Shift length:</span> {profile?.autopilot_shift_min_minutes == null ? 'Default minimum' : `${profile.autopilot_shift_min_minutes / 60}h minimum`} to {profile?.autopilot_shift_max_minutes == null ? 'default maximum' : `${profile.autopilot_shift_max_minutes / 60}h maximum`}</p>
              </div>
              {readinessLoading ? (
                <p className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" /> Rechecking setup before generation…</p>
              ) : !ready && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
                  <p className="font-medium">Generation is blocked until setup is ready.</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4">{(readiness?.blockers.length ? readiness.blockers : [readinessError ?? 'Recheck readiness.']).map((blocker, index) => <li key={`${index}-${blocker}`}>{blocker}</li>)}</ul>
                  <button type="button" onClick={() => setStep(0)} className="mt-2 text-amber-200 underline underline-offset-2">Back to setup</button>
                </div>
              )}
              <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/[0.06] p-3 text-xs leading-5 text-emerald-100">
                <strong>Nothing is published by this step.</strong> A review is staged in Huume. A manager must confirm it to create drafts, then publish separately when the schedule is right.
              </div>
            </>
          )}
        </div>
        <footer className="flex items-center justify-between gap-3 border-t border-zinc-800 px-5 py-4 sm:px-6">
          <button type="button" onClick={step === 0 ? () => leave('close') : () => setStep(step - 1)} disabled={saving || running} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:text-zinc-100 disabled:opacity-40">{step === 0 ? 'Cancel' : <><ArrowLeft className="h-3.5 w-3.5" /> Back</>}</button>
          {step === 0 && <button type="button" onClick={() => setStep(1)} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-500">Continue <ArrowRight className="h-3.5 w-3.5" /></button>}
          {step === 1 && <button type="button" onClick={() => { void continueFromPolicy() }} disabled={saving || profileLoading || !policy} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}{policyChanged ? 'Save & continue' : 'Continue'} <ArrowRight className="h-3.5 w-3.5" /></button>}
          {step === 2 && <button type="button" onClick={() => { void generate() }} disabled={!ready || running || saving || !profile} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40">{running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}{running ? 'Preparing review…' : 'Build review'}</button>}
        </footer>
      </section>
    </Modal>
  )
}
