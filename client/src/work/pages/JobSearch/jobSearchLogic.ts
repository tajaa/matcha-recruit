import { ApiError } from '../../../api/client'
import type {
  JobApproach, JobCompPart, JobLeadDetail, JobLeadSummary, JobSearchDetail, JobSearchStatusView,
  JobSearchSummary, JobSearchUsage, JobWeights,
} from '../../api/matchaWork/jobSearch'

// The pure rules behind the Job search page, ported from the macOS app's
// `JobSearchViewModel` / `JobSearchModels` so the two read a search the same way.

/** Gmail's drafts folder: where Draft email puts a job's first message. */
export const GMAIL_DRAFTS_URL = 'https://mail.google.com/mail/u/0/#drafts'

export const JOB_SEARCH_GUIDE_SEEN_KEY = 'espresso-job-search-guide-seen'

export const DEFAULT_WEIGHTS: JobWeights = { base: 0.45, bonus: 0.2, equity: 0.2, fit: 0.15 }

export const sameWeights = (a: JobWeights, b: JobWeights) =>
  a.base === b.base && a.bonus === b.bonus && a.equity === b.equity && a.fit === b.fit

export const anyWeightAboveZero = (w: JobWeights) => w.base + w.bonus + w.equity + w.fit > 0

export const LIVE_STATUSES = new Set(['queued', 'planning', 'discovering', 'screening', 'enriching', 'approaching'])

export const isLive = (status: string) => LIVE_STATUSES.has(status)

/** The server drafts more approaches only for a search that finished or was
 *  cancelled; a failed one has no ranked jobs to draft for. */
export const canDraft = (search: Pick<JobSearchSummary, 'status'>) =>
  search.status === 'done' || search.status === 'cancelled'

export const displayTitle = (search: Pick<JobSearchSummary, 'title' | 'ask'>) => search.title || search.ask

export function statusLabel(status: string): string {
  switch (status) {
    case 'queued': return 'Queued'
    case 'planning': return 'Planning'
    case 'discovering': return 'Searching'
    case 'screening': return 'Screening'
    case 'enriching': return 'Reading postings'
    case 'approaching': return 'Drafting approaches'
    case 'done': return 'Done'
    case 'failed': return "Didn't finish"
    case 'cancelled': return 'Cancelled'
    default: return capitalize(status)
  }
}

/** Plan → Search → Screen → Read pay → Draft approaches → Done. */
export const PHASES = ['Plan', 'Search', 'Screen', 'Read pay', 'Draft approaches', 'Done'] as const

/** Which phase a status is at, or null for one that is not a step (failed / cancelled). */
export function phaseIndex(status: string): number | null {
  switch (status) {
    case 'queued': case 'planning': return 0
    case 'discovering': return 1
    case 'screening': return 2
    case 'enriching': return 3
    case 'approaching': return 4
    case 'done': return 5
    default: return null
  }
}

// ─── Jobs ───

/** Ranked after every match because its fit is under the search's floor (the
 *  server's `BELOW_FLOOR_BAND`). */
export const BELOW_FLOOR_BAND = 8

export const isIrrelevant = (lead: JobLeadSummary) => lead.screen_status === 'irrelevant'
export const isBelowFloor = (lead: JobLeadSummary) => lead.rank_band === BELOW_FLOOR_BAND
export const isDrafting = (lead: JobLeadSummary) => lead.approach_status === 'queued' || lead.approach_status === 'drafting'
export const hasApproach = (lead: JobLeadSummary) => lead.approach_status === 'done'
/** A tailored résumé's download name ("Resume - Acme - COO.txt"), with only
 *  letters, digits and plain punctuation so it saves on any system. */
export function resumeFileName(lead: { company: string; title: string }): string {
  const part = (text: string) => text.replace(/[^\p{L}\p{N} .,&()'-]+/gu, ' ').replace(/\s+/g, ' ').trim().slice(0, 60)
  return `${['Resume', part(lead.company), part(lead.title)].filter(Boolean).join(' - ')}.txt`
}

/** Their résumé is being tailored to this job: the open job polls until it lands. */
export const isTailoring = (lead: JobLeadSummary) => lead.resume_status === 'queued' || lead.resume_status === 'drafting'
/** In Gmail drafts, waiting to be edited and sent. */
export const emailWaiting = (lead: JobLeadSummary) => !!lead.email_draft_id && !lead.email_sent_at

export const FILTERS = ['All', 'Drafted', 'Pay posted', 'Saved', 'Applied', 'Dismissed'] as const
export type JobFilter = (typeof FILTERS)[number]

export function filterLeads(leads: JobLeadSummary[], filter: JobFilter, showWeaker: boolean): JobLeadSummary[] {
  return leads.filter((lead) => {
    // Screened-out jobs and those under the search's fit floor hide from the
    // browsing tabs, never from the person's own lists: a job they saved or
    // applied to stays there.
    if ((isIrrelevant(lead) || isBelowFloor(lead)) && !showWeaker
      && (filter === 'All' || filter === 'Pay posted' || filter === 'Drafted')) {
      return false
    }
    switch (filter) {
      case 'All': return lead.user_state !== 'dismissed'
      case 'Drafted': return hasApproach(lead) && lead.user_state !== 'dismissed'
      case 'Pay posted': return lead.comp_status === 'posted' && lead.user_state !== 'dismissed'
      case 'Saved': return lead.user_state === 'saved'
      case 'Applied': return lead.user_state === 'applied'
      case 'Dismissed': return lead.user_state === 'dismissed'
    }
  })
}

/** Whether the cheap status says the jobs on screen are out of date. */
export const statusChanged = (detail: JobSearchDetail, status: JobSearchStatusView) =>
  status.fingerprint !== detail.fingerprint || status.status !== detail.status
  || status.lead_count !== detail.leads.length

/** Whether the page should keep polling: the search is still running, or a job is being drafted. */
export const needsPolling = (detail: JobSearchDetail) => isLive(detail.status) || detail.leads.some(isDrafting)

/** How many 3/5 jobs "Show more" would add: only for a finished search still
 *  at its first-pass floor of 4/5 (the server widens once). */
export function widerCount(detail: JobSearchDetail): number {
  if (detail.fit_floor !== 4 || !canDraft(detail)) return 0
  return detail.leads.filter((lead) =>
    isBelowFloor(lead) && !isIrrelevant(lead) && lead.fit_score === 3 && lead.user_state !== 'dismissed',
  ).length
}

export interface SearchProgress {
  drafted: number
  saved: number
  emailsWaiting: number
  emailsSent: number
  applied: number
}

/** Where a finished search stands, for its Next steps. */
export function searchProgress(leads: JobLeadSummary[]): SearchProgress {
  const out: SearchProgress = { drafted: 0, saved: 0, emailsWaiting: 0, emailsSent: 0, applied: 0 }
  for (const lead of leads) {
    if (lead.user_state === 'dismissed') continue
    // The jobs the Drafted tab shows by default: weaker matches are hidden there.
    if (hasApproach(lead) && !isIrrelevant(lead) && !isBelowFloor(lead)) out.drafted += 1
    if (lead.user_state === 'saved') out.saved += 1
    if (lead.user_state === 'applied') out.applied += 1
    if (emailWaiting(lead)) out.emailsWaiting += 1
    if (lead.email_sent_at) out.emailsSent += 1
  }
  return out
}

export function progressLine(p: SearchProgress): string | null {
  const parts = [
    p.saved > 0 ? `${p.saved} saved` : null,
    p.emailsWaiting > 0 ? (p.emailsWaiting === 1 ? '1 email in drafts' : `${p.emailsWaiting} emails in drafts`) : null,
    p.emailsSent > 0 ? `${p.emailsSent} sent` : null,
    p.applied > 0 ? `${p.applied} applied` : null,
  ].filter((part): part is string => part !== null)
  return parts.length ? parts.join(' · ') : null
}

/** The person's own state first, then where its first message is. */
export function leadStatusText(lead: JobLeadSummary): string {
  if (isIrrelevant(lead)) return 'Screened out'
  if (isBelowFloor(lead) && lead.user_state === 'new') return 'Weaker fit'
  if (lead.user_state === 'applied') return 'Applied'
  if (lead.email_sent_at) return 'Emailed'
  if (emailWaiting(lead)) return 'In drafts'
  return lead.user_state === 'new' ? '' : capitalize(lead.user_state)
}

export const showsRemoteBadge = (lead: JobLeadSummary) =>
  lead.remote === true && !lead.location.toLowerCase().includes('remote')

/** "4/5" style fit, or an en dash when the job was not screened. */
export const fitText = (fit: number | null | undefined) => (fit == null ? '–' : `${fit}/5`)

export function compBadge(status: string): string {
  if (status === 'posted') return 'Posted'
  if (status === 'mentioned') return 'Mentioned'
  return 'Not posted'
}

export function usageLine(usage: JobSearchUsage | null | undefined): string | null {
  if (!usage || usage.limit <= 0) return null
  return `${usage.remaining} of ${usage.limit} searches left this month`
}

// ─── Pay ───

/** "30", "12.5", "1.25": up to six significant digits and no exponent,
 *  matching the server's pay line (Python's `:g`). */
export function trimNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)))
}

function money(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: value < 1000 ? 2 : 0 })
}

export const dollars = (value: number) => `$${money(value)}`

/** A pay part as one line: "$250,000–$300,000 a year", "30% of base", "0.5–1%". */
export function partLine(name: string, part: JobCompPart): string {
  if (part.pct_min != null) {
    const lo = part.pct_min
    const hi = part.pct_max ?? lo
    const range = lo === hi ? `${trimNumber(lo)}%` : `${trimNumber(lo)}–${trimNumber(hi)}%`
    return name === 'Bonus' ? `${range} of base` : range
  }
  if (part.min != null) {
    const lo = part.min
    const hi = part.max ?? lo
    const currency = part.currency ?? 'USD'
    const symbol = currency === 'USD' ? '$' : `${currency} `
    const amount = lo === hi ? `${symbol}${money(lo)}` : `${symbol}${money(lo)}–${symbol}${money(hi)}`
    const period = part.period ? (part.period === 'hour' ? ' an hour' : ` a ${part.period}`) : ''
    return amount + period
  }
  return part.status === 'mentioned' ? 'Mentioned, no figure' : 'Not posted'
}

export function compParts(lead: JobLeadDetail): [string, JobCompPart][] {
  const comp = lead.comp ?? {}
  const parts: [string, JobCompPart | null | undefined][] = [['Base', comp.base], ['Bonus', comp.bonus], ['Equity', comp.equity]]
  return parts.filter((pair): pair is [string, JobCompPart] => !!pair[1])
}

export function evidenceLabel(origin: string | null | undefined): string {
  switch (origin) {
    case 'ats_api': return "From the job board's data"
    case 'jsonld': return "From the posting page's data"
    case 'google_jobs': return 'From Google Jobs'
    case 'page': return 'From the posting page'
    default: return 'From the posting'
  }
}

// ─── Approach ───

/** An approach with nothing in it is no approach (the server may send `{}`). */
export function usableApproach(approach: JobApproach | null | undefined): JobApproach | null {
  if (!approach) return null
  const empty = !approach.summary && !approach.steps?.length && !approach.answers?.length && !approach.cover_letter
  return empty ? null : approach
}

export function channelLabel(channel: string | null | undefined): string {
  switch (channel) {
    case 'referral': return 'Referral'
    case 'hiring_manager': return 'Hiring manager'
    case 'recruiter': return 'Recruiter'
    case 'search_firm': return 'Search firm'
    default: return 'Application portal'
  }
}

/** "[Hiring manager's name]"-style blanks a draft leaves for the person, in order, once each. */
export function placeholders(text: string): string[] {
  const out: string[] = []
  for (const match of text.matchAll(/\[[^[\]\n]{2,80}\]/g)) {
    if (!out.includes(match[0])) out.push(match[0])
  }
  return out
}

export const questionText = (q: { label?: string | null; question?: string | null; key?: string | null;
  question_key?: string | null }) => q.label || q.question || q.key || q.question_key || ''

/** Why Espresso left a question for the person: what kind of question it is. */
export function unansweredReason(kind: string | null | undefined): string | null {
  switch (kind) {
    case 'file': return 'a file to upload'
    case 'authorization': return 'work authorization'
    case 'demographic': return 'a voluntary demographic question'
    default: return null
  }
}

/** A posting's text as it reads best: each line trimmed (pages indent with
 *  spaces and non-breaking spaces), runs of spaces collapsed, and at most one
 *  blank line between paragraphs. */
export function tidyPosting(text: string): string {
  const lines = text.replace(/\r\n/g, '\n').replace(/\u00A0/g, ' ').split('\n')
    .map((line) => line.split(' ').filter(Boolean).join(' ').trim())
  const out: string[] = []
  for (const line of lines) {
    if (!line) {
      if (out.length && out[out.length - 1] !== '') out.push('')
    } else {
      out.push(line)
    }
  }
  while (out.length && out[out.length - 1] === '') out.pop()
  return out.join('\n')
}

/** Only plain http(s) links are opened. */
export function webUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname ? url.href : null
  } catch {
    return null
  }
}

export function hostOf(value: string): string {
  try { return new URL(value).hostname } catch { return value }
}

// ─── Starting a search ───

/** "COO, Chief Operating Officer" → ["COO", "Chief Operating Officer"], each once. */
export function splitList(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of text.split(/[,;\n]/)) {
    const item = raw.trim()
    if (!item || seen.has(item.toLowerCase())) continue
    seen.add(item.toLowerCase())
    out.push(item)
  }
  return out
}

/** The server's ceiling on a minimum base (`base_floor`, le=10,000,000). */
export const MAX_BASE_FLOOR = 10_000_000

export type BaseFloor = { kind: 'none' } | { kind: 'amount'; dollars: number } | { kind: 'invalid' }

/** "250000", "250,000", "$250,000.00", "250k", "$250K", "1.5M" or "1.5 mm" as
 *  dollars. Anything else, or more than the server takes, is invalid rather
 *  than quietly read as some other number. */
export function parseBaseFloor(text: string): BaseFloor {
  let s = text.toLowerCase().replace(/usd/g, '').replace(/[$,_\s]/g, '')
  if (!s) return { kind: 'none' }
  let multiplier = 1
  if (s.endsWith('mm')) { multiplier = 1_000_000; s = s.slice(0, -2) }
  else if (s.endsWith('m')) { multiplier = 1_000_000; s = s.slice(0, -1) }
  else if (s.endsWith('k')) { multiplier = 1_000; s = s.slice(0, -1) }
  if (!s || !/^[0-9.]+$/.test(s)) return { kind: 'invalid' }
  const number = Number(s)
  if (!Number.isFinite(number)) return { kind: 'invalid' }
  const amount = Math.round(number * multiplier)
  if (amount < 0 || amount > MAX_BASE_FLOOR) return { kind: 'invalid' }
  return { kind: 'amount', dollars: amount }
}

/** Whether a failed start means a retry is a new request. Only when the
 *  server answered that it didn't start one: a refusal (4xx), or a 503 for a
 *  search it couldn't queue (marked failed, which is free). With no answer, or
 *  any other error, the search may be running, so the retry keeps the request
 *  id and the server hands back that search. */
export function retryIsNewRequest(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  return (error.status >= 400 && error.status < 500) || error.status === 503
}

/** The server's structured refusal (`detail`), if it sent one. */
function errorDetail(error: unknown): Record<string, unknown> | null {
  if (!(error instanceof ApiError)) return null
  const body = error.body
  if (!body || typeof body !== 'object' || !('detail' in body)) return null
  const detail = (body as { detail: unknown }).detail
  return detail && typeof detail === 'object' ? detail as Record<string, unknown> : null
}

/** The server's structured refusal code (`detail.code`), if it sent one. */
export function errorCode(error: unknown): string | null {
  const code = errorDetail(error)?.code
  return typeof code === 'string' ? code : null
}

/** The job as it is now, sent with a refusal about it (`email_draft_missing`). */
export function errorLead(error: unknown): JobLeadDetail | null {
  const lead = errorDetail(error)?.lead
  return lead && typeof lead === 'object' && typeof (lead as { id?: unknown }).id === 'string'
    ? lead as JobLeadDetail
    : null
}

/** What went wrong, as one line: the server's own words, or the fallback. */
export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message ? error.message : fallback
}

/** What "Ask Espresso" puts in the conversation's composer for one job. The
 *  same words the macOS app hands over, so the assistant's `jobs` ability
 *  reads the job the same way from either. */
export function askEspressoPrompt(searchId: string, jobId: string): string {
  return `Help me with the job ${jobId} in my job search ${searchId}. Read the job first: the posting, its pay `
    + 'evidence and the drafted approach. Then help me tighten the outreach, the application answers and '
    + "the cover letter. Don't send or apply for anything.\n\nMy instructions: "
}

function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}
