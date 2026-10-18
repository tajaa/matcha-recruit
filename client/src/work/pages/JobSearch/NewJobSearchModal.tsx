import { useEffect, useRef, useState } from 'react'
import { FileText, Loader2, X } from 'lucide-react'
import { ApiError, parsePlanRequired } from '../../../api/client'
import { getMyResume, uploadMyResume, type ProfileResume } from '../../../api/profileResume'
import type { JobSearchCreate, JobSearchSetup, JobSearchSummary, RemotePreference } from '../../api/matchaWork/jobSearch'
import {
  DEFAULT_WEIGHTS, anyWeightAboveZero, dollars, errorText, parseBaseFloor, retryIsNewRequest, sameWeights,
  splitList, usageLine,
} from './jobSearchLogic'
import WeightSliders from './WeightSliders'

const RESUME_TYPES = '.pdf,.doc,.docx,.txt'

const fieldLabel = 'mb-1.5 block text-[11px] font-semibold text-w-text'
const inputClass = 'w-full rounded-md border border-w-line bg-w-surface2/60 px-2.5 py-1.5 text-xs text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/60'

/**
 * Start a job search: what they're after, what matters most, and whether to
 * use their résumé. The first search also shows what Job search does with
 * their data, and starts only once they agree. Mirrors the macOS app's
 * New job search sheet.
 */
export default function NewJobSearchModal({ list, loadError, onRetry, onCreate, onCreated, onClose }: {
  list: JobSearchSetup | null
  loadError?: string | null
  onRetry?: () => void
  onCreate: (body: JobSearchCreate) => Promise<JobSearchSummary>
  onCreated: (search: JobSearchSummary) => void
  onClose: () => void
}) {
  const [ask, setAsk] = useState('')
  const [titles, setTitles] = useState('')
  const [locations, setLocations] = useState('')
  const [remote, setRemote] = useState<RemotePreference>('any')
  const [baseFloor, setBaseFloor] = useState('')
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS)
  const [resume, setResume] = useState<ProfileResume | null>(null)
  const [resumeLoaded, setResumeLoaded] = useState(false)
  const [useResume, setUseResume] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(crypto.randomUUID())
  /** A résumé was uploaded here: the saved one's read, if still out, is older. */
  const uploaded = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)

  const consent = list?.consent ?? null
  const needsConsent = !(consent?.granted ?? false)
  const floor = parseBaseFloor(baseFloor)
  const canStart = ask.trim().length >= 3 && anyWeightAboveZero(weights) && (!needsConsent || agreed)
    && !!list && !loadError && !starting && !uploading && floor.kind !== 'invalid'
  const usage = usageLine(list?.usage)

  useEffect(() => {
    let cancelled = false
    getMyResume()
      .then((saved) => {
        // An upload since says what the résumé is; this answer would undo it.
        if (!cancelled && !uploaded.current) { setResume(saved); setUseResume(!!saved) }
      })
      .catch(() => { /* no résumé is fine */ })
      .finally(() => { if (!cancelled) setResumeLoaded(true) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    dialogRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !starting) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, starting])

  async function pickResume(file: File) {
    setUploading(true)
    setError(null)
    try {
      const saved = await uploadMyResume(file)
      uploaded.current = true
      setResume(saved)
      setUseResume(true)
      setResumeLoaded(true)
    } catch (e) {
      setError(errorText(e, "Couldn't read that résumé."))
    } finally {
      setUploading(false)
    }
  }

  async function start() {
    if (!canStart) return
    setStarting(true)
    setError(null)
    const criteriaTitles = splitList(titles).slice(0, 8)
    const body: JobSearchCreate = {
      request_id: requestId.current,
      title: criteriaTitles[0] ?? '',
      ask: ask.trim(),
      criteria: {
        titles: criteriaTitles,
        locations: splitList(locations).slice(0, 6),
        remote,
        base_floor: floor.kind === 'amount' ? floor.dollars : null,
        currency: 'USD',
        exclude_companies: [],
        deal_breakers: [],
      },
      weights: sameWeights(weights, DEFAULT_WEIGHTS) ? null : weights,
      use_resume: useResume && !!resume,
      consent_version: needsConsent && agreed ? consent?.disclosure?.version ?? null : null,
    }
    try {
      onCreated(await onCreate(body))
    } catch (e) {
      // A plan the person doesn't have: the paywall is already up.
      if (e instanceof ApiError && e.status === 403 && parsePlanRequired(e.body)) {
        onClose()
        return
      }
      setError(errorText(e, "Couldn't start the search."))
      // Only a clear refusal makes the retry a new request. After a timeout or
      // a dropped connection the search may have started, so the retry keeps
      // the request id and the server returns that search instead of refusing
      // a second live one or counting another.
      if (retryIsNewRequest(e)) requestId.current = crypto.randomUUID()
    } finally {
      setStarting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-end justify-center bg-black/70 sm:items-center sm:px-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !starting) onClose() }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="New job search"
        className="flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-t-2xl border border-w-line bg-w-surface shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-w-line px-5 py-3.5">
          <h2 className="text-sm font-semibold text-w-text">New job search</h2>
          <button type="button" onClick={onClose} disabled={starting} aria-label="Close" className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-w-text">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label htmlFor="js-ask" className={fieldLabel}>What are you looking for?</label>
            <textarea
              id="js-ask"
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              rows={3}
              maxLength={4000}
              className={`${inputClass} resize-none`}
            />
            <p className="mt-1 text-[10px] text-w-dim">
              e.g. “COO roles across the US. I care most about salary, bonus and equity; Series B or later; no relocation.”
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="js-titles" className={fieldLabel}>Titles (optional)</label>
              <input id="js-titles" value={titles} onChange={(e) => setTitles(e.target.value)} placeholder="COO, Chief Operating Officer" className={inputClass} />
            </div>
            <div>
              <label htmlFor="js-locations" className={fieldLabel}>Locations (optional)</label>
              <input id="js-locations" value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="United States, Austin TX, Remote" className={inputClass} />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="js-remote" className={fieldLabel}>Remote</label>
              <select id="js-remote" value={remote} onChange={(e) => setRemote(e.target.value as RemotePreference)} className={inputClass}>
                <option value="any">Any</option>
                <option value="remote_only">Remote only</option>
                <option value="onsite_only">On-site only</option>
              </select>
            </div>
            <div>
              <label htmlFor="js-floor" className={fieldLabel}>Minimum base (USD, optional)</label>
              <input id="js-floor" value={baseFloor} onChange={(e) => setBaseFloor(e.target.value)} placeholder="250000 or $250k" className={inputClass} />
              {floor.kind === 'amount' && <p className="mt-1 text-[10px] text-w-dim">Using {dollars(floor.dollars)} a year</p>}
              {floor.kind === 'invalid' && <p className="mt-1 text-[10px] text-amber-500">Enter an amount like 250000, $250k or 1.5M (up to $10M).</p>}
            </div>
          </div>

          <div>
            <p className={fieldLabel}>What matters most</p>
            <WeightSliders weights={weights} onChange={setWeights} />
            <p className="mt-1.5 text-[10px] leading-4 text-w-dim">
              Pay is only what a posting states, with the text it came from. Jobs that don't post pay are ranked
              after those that do; unposted pay is never counted as zero.
            </p>
          </div>

          <div>
            <p className={fieldLabel}>Your résumé</p>
            <div className="flex items-center gap-2">
              <FileText size={15} className="shrink-0 text-w-dim" />
              <div className="min-w-0 flex-1">
                {!resumeLoaded ? (
                  <Loader2 size={14} className="animate-spin text-w-dim" />
                ) : resume ? (
                  <>
                    <p className="truncate text-xs font-medium text-w-text">{resume.filename || 'Résumé'}</p>
                    {resume.parsed_data?.current_title && <p className="truncate text-[10px] text-w-dim">{resume.parsed_data.current_title}</p>}
                  </>
                ) : (
                  <p className="text-xs text-w-dim">No résumé saved</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-xs text-w-text hover:bg-w-surface2 disabled:opacity-50"
              >
                {uploading && <Loader2 size={12} className="animate-spin" />}
                {resume ? 'Replace…' : 'Upload…'}
              </button>
              <input
                ref={fileInput}
                type="file"
                accept={RESUME_TYPES}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ''
                  if (file) void pickResume(file)
                }}
              />
            </div>
            <label className={`mt-2 flex items-center gap-2 text-[11px] ${resume ? 'text-w-text' : 'text-w-faint'}`}>
              <input type="checkbox" checked={useResume && !!resume} disabled={!resume} onChange={(e) => setUseResume(e.target.checked)} />
              Use my résumé to judge fit and draft the answers and cover letter
            </label>
          </div>

          {needsConsent && consent?.disclosure && (
            <div className="rounded-lg bg-w-surface2/60 p-3">
              <p className="text-xs font-semibold text-w-text">{consent.disclosure.title}</p>
              <ul className="mt-1.5 space-y-1">
                {consent.disclosure.body.map((line) => (
                  <li key={line} className="text-[11px] leading-4 text-w-dim">• {line}</li>
                ))}
              </ul>
              <label className="mt-2 flex items-center gap-2 text-[11px] text-w-text">
                <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                I agree
              </label>
            </div>
          )}

          {loadError && (
            <div role="alert" className="space-y-2 rounded-lg bg-amber-500/10 p-3 text-[11px] text-amber-500">
              <p>{loadError}</p>
              {onRetry && <button type="button" onClick={onRetry} className="font-semibold text-w-accent hover:underline">Try again</button>}
            </div>
          )}
          {!list && !loadError && <p role="status" className="text-[11px] text-w-dim">Loading job search…</p>}
          {error && <p role="alert" className="text-[11px] text-amber-500">{error}</p>}
        </div>

        <div className="flex items-center gap-3 border-t border-w-line px-5 py-3">
          {usage && <p className="text-[10px] text-w-dim">{usage}</p>}
          <div className="flex-1" />
          <button type="button" onClick={onClose} disabled={starting} className="rounded-md px-3 py-1.5 text-xs text-w-dim hover:text-w-text">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void start()}
            disabled={!canStart}
            className="inline-flex min-w-[96px] items-center justify-center gap-1.5 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi disabled:opacity-40"
          >
            {starting ? <Loader2 size={13} className="animate-spin" /> : 'Start search'}
          </button>
        </div>
      </div>
    </div>
  )
}
