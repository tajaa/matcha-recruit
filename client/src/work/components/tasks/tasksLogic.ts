import { ApiError } from '../../../api/client'
import type {
  AgentTask, AgentTaskActionRun, AgentTaskCard, AgentTaskColumn, AgentTaskDetail, AgentTaskField, AgentTaskHomes,
  AgentTaskItem, AgentTaskItemDetail, AgentTaskRoundSummary, AgentTaskStatusView, AgentTasksSummary, AgentTaskUnit,
  AgentTaskUsage, IntakeFormField,
} from '../../types'

// The pure rules behind the Tasks page and the task cards in chat, ported from
// the macOS app (`AgentTaskModels`, `TasksViewModel`, `TaskItemDetailView`,
// `TaskActionFlow`, `TaskChatCards`) so the two read a task the same way.

// ─── Tasks ───

export const isLive = (task: Pick<AgentTask, 'status'>) => task.status === 'queued' || task.status === 'running'
export const isWaiting = (task: Pick<AgentTask, 'status'>) => task.status === 'waiting'
/** A job search: its own view opens inside Tasks. */
export const isJobSearch = (task: Pick<AgentTask, 'engine' | 'job_search_id'>) =>
  task.engine === 'job_search' && !!task.job_search_id
export const displayTitle = (task: Pick<AgentTask, 'title' | 'directive'>) => task.title || task.directive || ''

export function phaseLabel(phase: string | null | undefined): string {
  switch (phase) {
    case 'plan': return 'Planning…'
    case 'providers': case 'discover': return 'Searching…'
    case 'enrich': return 'Reading pages…'
    case 'screen': return 'Checking what fits…'
    case 'rank': return 'Ranking…'
    case 'summarize': return 'Writing it up…'
    case 'refine': return 'Reading your change…'
    // A job search's own phases.
    case 'planning': return 'Planning…'
    case 'discovering': return 'Searching…'
    case 'screening': return 'Checking what fits…'
    case 'enriching': return 'Reading postings…'
    case 'approaching': return 'Drafting approaches…'
    default: return 'Working…'
  }
}

export function statusLabel(task: Pick<AgentTask, 'status' | 'phase'>): string {
  switch (task.status) {
    case 'queued': return 'Starting…'
    case 'running': return phaseLabel(task.phase)
    case 'waiting': return 'Needs you'
    case 'done': return 'Done'
    case 'failed': return 'Stopped'
    case 'cancelled': return 'Cancelled'
    default: return capitalize(task.status)
  }
}

/** The list's groups, in the order they show. */
export const GROUPS = ['Needs you', 'Running', 'Done'] as const
export type TaskGroup = (typeof GROUPS)[number]

export function groupOf(task: Pick<AgentTask, 'status'>): TaskGroup {
  if (isWaiting(task)) return 'Needs you'
  if (isLive(task)) return 'Running'
  return 'Done'
}

const time = (value: string | null | undefined) => {
  const parsed = value ? Date.parse(value) : Number.NaN
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed
}

/** Non-empty groups with their tasks, newest first within each. */
export function groupTasks<T extends AgentTask>(tasks: T[]): [TaskGroup, T[]][] {
  return GROUPS.flatMap((group): [TaskGroup, T[]][] => {
    const members = tasks.filter((t) => groupOf(t) === group).sort((a, b) => time(b.created_at) - time(a.created_at))
    return members.length ? [[group, members]] : []
  })
}

/** The first task the list shows, opened when none is. */
export function firstTask<T extends AgentTask>(tasks: T[]): T | null {
  return groupTasks(tasks)[0]?.[1][0] ?? null
}

/** What its row says beside the status: "Apartments ·", and "· 12 found". */
export function rowMeta(task: AgentTask): { kind: string | null; count: string | null } {
  const jobs = isJobSearch(task)
  const shown = task.shown_count ?? 0
  return {
    kind: !jobs && task.playbook_label ? task.playbook_label : null,
    count: shown > 0 ? `${shown} ${jobs ? 'jobs' : 'found'}` : null,
  }
}

export function usageLine(usage: AgentTaskUsage | null | undefined): string | null {
  if (!usage || usage.limit <= 0) return null
  return `${usage.remaining} of ${usage.limit} task units left this month`
}

/** The sidebar badge: how many run, and whether something needs the person. */
export function badge(summary: AgentTasksSummary | null | undefined): { count: number; attention: boolean } {
  if (!summary) return { count: 0, attention: false }
  return { count: summary.running, attention: summary.waiting > 0 || summary.unseen > 0 }
}

/** How often to poll: quickly while something runs, slowly otherwise. */
export const pollMs = (live: boolean) => (live ? 4_000 : 30_000)

/** Whether the cheap status says what is on screen is out of date. */
export const statusChanged = (detail: Pick<AgentTaskDetail, 'fingerprint' | 'status'>, status: AgentTaskStatusView) =>
  status.fingerprint !== detail.fingerprint || status.status !== detail.status

// ─── A task's detail ───

/** The newest round's summary that says something (a document round never does). */
export function latestSummary(detail: Pick<AgentTaskDetail, 'rounds'>): AgentTaskRoundSummary | null {
  const rounds = detail.rounds ?? []
  for (let i = rounds.length - 1; i >= 0; i -= 1) {
    const round = rounds[i]
    if (round.kind !== 'document' && round.summary?.headline) return round.summary
  }
  return null
}

/** Refine and Search more: a finished (or waiting) task that isn't a job search. */
export const canFollowUp = (detail: AgentTaskDetail) =>
  !isJobSearch(detail) && (detail.status === 'done' || detail.status === 'waiting')

/** What it's looking for, as chips: where, then each limit. */
export function planChips(detail: Pick<AgentTaskDetail, 'plan'>): string[] {
  const plan = detail.plan
  if (!plan) return []
  return [plan.location, ...(plan.constraints ?? []).map((c) => c.label)].filter((s): s is string => !!s)
}

/** The journal note a document round just wrote, if it wrote one. */
export const documentJournalId = (detail: Pick<AgentTaskDetail, 'rounds'>) => {
  const last = detail.rounds?.[detail.rounds.length - 1]
  return last?.kind === 'document' ? last.document?.journal_id ?? null : null
}

export function roundLabel(kind: string): string {
  switch (kind) {
    case 'initial': return 'First search'
    case 'refine': return 'Refined'
    case 'more': return 'Searched for more'
    case 'document': return 'Document'
    default: return capitalize(kind)
  }
}

// ─── Findings ───

/** Hidden from the list unless asked: it breaks a limit, didn't fit, is gone,
 *  or the person dismissed it. */
export const isHidden = (item: Pick<AgentTaskItem, 'rank_band'>) => (item.rank_band ?? 0) >= 9

export const FILTERS = ['Fits', 'Saved', 'Hidden'] as const
export type FindingFilter = (typeof FILTERS)[number]

export function filterItems<T extends AgentTaskItem>(items: T[], filter: FindingFilter): T[] {
  switch (filter) {
    case 'Fits': return items.filter((i) => !isHidden(i))
    case 'Saved': return items.filter((i) => i.user_state === 'saved' || i.user_state === 'chosen')
    case 'Hidden': return items.filter(isHidden)
  }
}

/** The facts it was asked for that can't be confirmed from its own page. */
export function unconfirmed(item: Pick<AgentTaskItem, 'flags'>): string[] {
  return (item.flags ?? []).filter((f) => f.startsWith('unconfirmed:')).map((f) => f.slice('unconfirmed:'.length))
}

export function hiddenReason(item: AgentTaskItem & Partial<Pick<AgentTaskItemDetail, 'violations'>>): string | null {
  if (item.user_state === 'dismissed') return 'Dismissed'
  const flags = item.flags ?? []
  if (flags.includes('unavailable')) return 'No longer available'
  const rule = item.violations?.[0]?.rule
  if (rule) return `Breaks a limit: ${rule}`
  if (flags.includes('irrelevant')) return 'Not a fit'
  return null
}

export const isVerified = (field: Pick<AgentTaskField, 'status'>) => field.status === 'verified'

/** "price_per_month" → "Price Per Month", for a fact the plan didn't name. */
export function labelFor(key: string): string {
  return key.split('_').filter(Boolean).map(capitalize).join(' ')
}

/** A fact's label: the plan's column, else its key in words. */
export function columnLabel(key: string, columns: AgentTaskColumn[] | null | undefined): string {
  return columns?.find((c) => c.key === key)?.label ?? labelFor(key)
}

/** The plan's columns first, in its order, then any other fact. */
export function factOrder(item: Pick<AgentTaskItem, 'fields'>, columns: AgentTaskColumn[] | null | undefined): string[] {
  const fields = item.fields ?? {}
  const first = (columns ?? []).map((c) => c.key).filter((k) => fields[k] != null)
  return [...first, ...Object.keys(fields).filter((k) => !first.includes(k)).sort()]
}

/** The facts a row shows: the plan's first five columns it has. */
export function rowFacts(item: Pick<AgentTaskItem, 'fields'>, columns: AgentTaskColumn[] | null | undefined) {
  const fields = item.fields ?? {}
  return (columns ?? []).slice(0, 5).flatMap((c) => (fields[c.key] ? [{ key: c.key, label: c.label, field: fields[c.key] }] : []))
}

export function originLabel(origin: string | null | undefined): string {
  switch (origin) {
    case 'provider': return 'From the listings provider'
    case 'leasing': return "From the building's leasing system"
    case 'jsonld': return "From the page's structured data"
    case 'page_text': case 'browser': return "From the page's text"
    case 'model': return 'Quoted by Espresso'
    default: return ''
  }
}

// ─── An apartment building's homes ───

/** Homes shown before "Show all". */
export const HOMES_SHOWN = 6

export const dollars = (value: number) =>
  `$${Math.round(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

/** "3 of 18 homes fit · from $2,949/mo", or "18 homes listed". */
export function homesLine(homes: AgentTaskHomes): string {
  const noun = homes.count === 1 ? 'home' : 'homes'
  const from = homes.from != null ? ` · from ${dollars(homes.from)}/mo` : ''
  if (homes.fit == null) return `${homes.count} ${noun} listed${from}`
  if (homes.fit === 0) return `None of ${homes.count} ${noun} fit`
  return `${homes.fit} of ${homes.count} ${noun} fit${from}`
}

/** The homes that meet every limit first, each group as the server sent it (cheapest first). */
export function homesOrder(units: AgentTaskUnit[]): AgentTaskUnit[] {
  return [...units.filter((u) => u.fits === true), ...units.filter((u) => u.fits !== true)]
}

/** "#B201 · Floor 2 · 2 bd · 1 ba · 910 sq ft" */
export function layoutLine(unit: AgentTaskUnit): string {
  const parts = [unit.number ? `#${unit.number}` : 'A home']
  if (unit.floor) parts.push(`Floor ${unit.floor}`)
  if (unit.beds != null) parts.push(unit.beds === 0 ? 'Studio' : `${unit.beds} bd`)
  if (unit.baths != null) parts.push(`${unit.baths} ba`)
  if (unit.sqft != null && unit.sqft > 0) parts.push(`${dollars(unit.sqft).slice(1)} sq ft`)
  return parts.join(' · ')
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** The local day as YYYY-MM-DD. */
function localDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** When it can be moved into: "Now" once the day has come (where the person
 *  is), else "Nov 4" ("Jan 25, 2027" in another year). */
export function availableLabel(unit: Pick<AgentTaskUnit, 'available'>, today: Date = new Date()): string | null {
  const iso = (unit.available ?? '').slice(0, 10)
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return null
  const month = Number(match[2])
  const day = Number(match[3])
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  const now = localDay(today)
  if (iso <= now) return 'Now'
  const shown = `${MONTHS[month - 1]} ${day}`
  return match[1] === now.slice(0, 4) ? shown : `${shown}, ${match[1]}`
}

/** "Available now · 12-month lease · Plan A2" */
export function unitTerms(unit: AgentTaskUnit, today: Date = new Date()): string {
  const available = availableLabel(unit, today)
  return [
    available && (available === 'Now' ? 'Available now' : `Available ${available}`),
    unit.lease_months != null ? `${unit.lease_months}-month lease` : null,
    unit.plan,
  ].filter(Boolean).join(' · ')
}

// ─── Actions on a finding (Buy, Apply) ───

export type ActionStage = 'details' | 'review' | 'working' | 'finished'

/** Where an action stands. `running` is a yes still being carried out (a
 *  confirm that was retried while the first one ran), not an outcome. */
export function actionStage(run: AgentTaskActionRun | null | undefined): ActionStage {
  if (!run) return 'details'
  if (run.status === 'proposed') return 'review'
  return run.status === 'running' ? 'working' : 'finished'
}

/** How often, and how many times, a running yes is read again before the
 *  sheet stops and says it's still going (about a minute). Reading it again is
 *  the same confirm call, which only reports a yes already given. */
export const RUNNING_READ_MS = 1_500
export const RUNNING_READS = 40

/** What the person typed for an action's own fields, trimmed; blanks left out. */
export function actionParams(values: Record<string, string>, fields: IntakeFormField[] | null | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  for (const field of fields ?? []) {
    const value = (values[field.key] ?? '').trim()
    if (value) out[field.key] = value
  }
  return out
}

export const isFinishedRun = (run: AgentTaskActionRun) => run.status === 'done' || run.status === 'failed'

/** "Checkout opened at drbronner.com", or why it didn't go through. */
export function doneLine(run: AgentTaskActionRun): string {
  const label = run.label || run.action || 'It'
  if (run.status === 'done') return run.result?.headline || label
  return `${label} didn't go through${run.error ? `: ${run.error}` : '.'}`
}

// ─── Forms (an action's fields, and the form Espresso asks in chat) ───

/** A field's starting text, from whatever value the server sent. */
export function initialText(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (Array.isArray(value)) return value.map(initialText).filter(Boolean).join(', ')
  return ''
}

export function placeholder(field: Pick<IntakeFormField, 'type'>): string {
  switch (field.type) {
    case 'money': return '$3,500'
    case 'number': return 'A number'
    case 'date': return 'YYYY-MM-DD'
    case 'time': return '19:30'
    case 'list': case 'multi_select': return 'Separate with commas or semicolons'
    case 'location': return 'A city, neighborhood or address'
    default: return ''
  }
}

/** A typed list split the way the server splits it: semicolons and new lines
 *  separate items when there are any, so "New York, NY; Remote" stays two
 *  places; otherwise commas do ("COO, VP Ops"). */
export function splitList(raw: string): string[] {
  const parts = /[;\n]/.test(raw) ? raw.split(/[;\n]/) : raw.split(',')
  return parts.map((s) => s.trim()).filter(Boolean)
}

/** One typed answer as the value the server takes, or undefined when it doesn't look right. */
export function parseField(field: IntakeFormField, raw: string): unknown {
  switch (field.type) {
    case 'number': case 'money': {
      const cleaned = raw.replace(/[,$]/g, '').trim().toLowerCase()
      const thousands = cleaned.endsWith('k')
      const digits = thousands ? cleaned.slice(0, -1) : cleaned
      if (!/^\d*\.?\d+$/.test(digits)) return undefined
      const number = Number(digits)
      return Number.isFinite(number) && number >= 0 ? number * (thousands ? 1_000 : 1) : undefined
    }
    case 'date': {
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw)
      if (!match) return undefined
      const [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3])]
      const date = new Date(Date.UTC(y, m - 1, d))
      return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d ? raw : undefined
    }
    case 'time': {
      const match = /^(\d{1,2}):(\d{1,2})$/.exec(raw)
      if (!match) return undefined
      const [h, m] = [Number(match[1]), Number(match[2])]
      return h < 24 && m < 60 ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}` : undefined
    }
    case 'boolean': {
      const lower = raw.toLowerCase()
      if (lower === 'yes' || lower === 'true') return true
      if (lower === 'no' || lower === 'false') return false
      return undefined
    }
    case 'select':
      return (field.options ?? []).includes(raw) ? raw : undefined
    case 'list': case 'multi_select': {
      const items = splitList(raw)
      if (field.type === 'multi_select' && items.some((i) => !(field.options ?? []).includes(i))) return undefined
      return items.length ? items : undefined
    }
    default:
      return raw
  }
}

/** What the person typed, as the values the server takes, with what is wrong
 *  in their words. Empty text is "not given"; files go as input ids, so a file
 *  field only checks that a required one has something. */
export function buildFormValues(
  fields: IntakeFormField[],
  text: Record<string, string>,
  files: Record<string, unknown[]> = {},
): { values: Record<string, unknown>; problems: string[] } {
  const values: Record<string, unknown> = {}
  const problems: string[] = []
  for (const field of fields) {
    if (field.type === 'file') {
      if (field.required && !(files[field.key]?.length)) problems.push(`${field.label} is needed.`)
      continue
    }
    if (field.type === 'consent') continue
    const raw = (text[field.key] ?? '').trim()
    if (!raw) {
      if (field.required) problems.push(`${field.label} is needed.`)
      continue
    }
    const value = parseField(field, raw)
    if (value === undefined) problems.push(`${field.label} doesn't look right.`)
    else values[field.key] = value
  }
  return { values, problems }
}

/** A refused form's field-by-field reasons (`detail.errors`), else the server's words. */
export function formErrorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'detail' in error.body) {
    const detail = (error.body as { detail: unknown }).detail
    if (detail && typeof detail === 'object' && 'errors' in detail) {
      const errors = (detail as { errors: unknown }).errors
      if (errors && typeof errors === 'object') {
        const lines = Object.keys(errors).sort()
          .map((k) => (errors as Record<string, unknown>)[k])
          .filter((v): v is string => typeof v === 'string' && !!v)
        if (lines.length) return lines.join(' ')
      }
    }
  }
  return errorText(error, fallback)
}

// ─── A task's card in chat ───

export function taskCardLead(card: Pick<AgentTaskCard, 'event' | 'status'>): string {
  if (card.event === 'started') return 'Started a task'
  switch (card.status) {
    case 'done': return 'Task done'
    case 'failed': return 'Task stopped'
    case 'waiting': return 'Task needs you'
    default: return 'Task'
  }
}

export function taskCardBody(card: Pick<AgentTaskCard, 'event' | 'headline' | 'note'>): string | null {
  if (card.event === 'started') return "It runs in the background. I'll post here when it's done."
  return card.headline || card.note || null
}

/** Up to four of a card finding's facts, in a steady order. */
export function cardFacts(fields: Record<string, string | null> | null | undefined): string {
  return Object.values(fields ?? {}).filter((v): v is string => !!v).sort().slice(0, 4).join(' · ')
}

// ─── Links and errors ───

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

/** What a link is called: the site ("drbronner.com"), or which part of
 *  Google it is when a finding only has Google's page. */
export function linkLabel(value: string): string {
  let url: URL
  try { url = new URL(value) } catch { return 'Open its page' }
  const host = url.hostname.toLowerCase()
  if (!host) return 'Open its page'
  const site = host.startsWith('www.') ? host.slice(4) : host
  if (!site.split('.').includes('google')) return site
  const path = url.pathname.toLowerCase()
  if (path.startsWith('/maps')) return 'Google Maps'
  if (path.startsWith('/shopping') || url.search.includes('ibp=oshop')) return 'Google Shopping'
  return site
}

/** What went wrong, as one line: the server's own words, or the fallback. */
export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message ? error.message : fallback
}

/** What "Ask Espresso" puts in the conversation's composer about a task (and
 *  one of its findings): the same words the macOS app hands over, so the
 *  assistant's `tasks` ability reads it the same way from either. */
export function askEspressoPrompt(taskId: string, itemId?: string | null): string {
  if (itemId) return `Help me with the finding ${itemId} in my task ${taskId}. Read the task first.\n\nMy instructions: `
  return `Help me with my task ${taskId}. Read it first.\n\nMy instructions: `
}

function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}
