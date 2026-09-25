import type { ReplayEvent, ReplayTask, WeeklyReplay } from '../api/matchaWork/replay'

export interface ReplayCard extends ReplayTask {
  task_id: string
  is_deleted: boolean
}

const PACIFIC = 'America/Los_Angeles'

function pacificDateParts(instant: Date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: PACIFIC, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(instant)
  const part = (name: string) => Number(parts.find((value) => value.type === name)?.value)
  return { year: part('year'), month: part('month'), day: part('day') }
}

/** Monday 00:00 in Los Angeles, independent of the viewer's local timezone. */
export function pacificWeekStart(instant: Date, offsetWeeks = 0): string {
  const { year, month, day } = pacificDateParts(instant)
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  const monday = new Date(Date.UTC(year, month - 1, day - (weekday + 6) % 7 + offsetWeeks * 7))
  // Probe at Pacific noon on Monday. DST transitions occur on Sunday; noon
  // and midnight on the same Monday have the same UTC offset.
  const probe = new Date(monday.getTime() + 12 * 60 * 60 * 1000)
  const zone = new Intl.DateTimeFormat('en-US', {
    timeZone: PACIFIC, timeZoneName: 'shortOffset',
  }).formatToParts(probe).find((part) => part.type === 'timeZoneName')?.value ?? 'GMT-8'
  const match = /^GMT([+-])(\d{1,2})(?::(\d{2}))?$/.exec(zone)
  if (!match) throw new Error(`Unexpected Pacific UTC offset: ${zone}`)
  const offsetMinutes = (Number(match[2]) * 60 + Number(match[3] ?? 0)) * (match[1] === '+' ? 1 : -1)
  return new Date(monday.getTime() - offsetMinutes * 60_000).toISOString()
}

export function foldReplay(replay: WeeklyReplay, count: number): ReplayCard[] {
  const cards = new Map<string, ReplayCard>()
  for (const row of replay.starting_state) {
    if (row.task_id && row.column !== 'done') cards.set(row.task_id, { ...row, task_id: row.task_id, is_deleted: false })
  }
  for (const event of replay.events.slice(0, Math.max(0, count))) {
    const id = event.task_id
    if (!id) continue
    if (event.event_type === 'created') {
      cards.set(id, { task_id: id, title: event.title, column: event.to_column ?? 'todo',
        assignee_name: null, assignee_avatar_url: null, is_deleted: false })
    } else if (['column_change', 'review_rejected', 'review_approved'].includes(event.event_type) && event.to_column) {
      const existing = cards.get(id)
      cards.set(id, existing ? { ...existing, column: event.to_column } : {
        task_id: id, title: event.title, column: event.to_column,
        assignee_name: null, assignee_avatar_url: null, is_deleted: false,
      })
    } else if (event.event_type === 'deleted') {
      const existing = cards.get(id)
      if (existing) cards.set(id, { ...existing, is_deleted: true })
    }
  }
  return [...cards.values()].sort((left, right) => left.task_id.localeCompare(right.task_id))
}

export function replayRoundIndex(events: ReplayEvent[], taskId: string, timestamp: string): number {
  const at = Date.parse(timestamp)
  return 1 + events.filter((event) => event.task_id === taskId && event.event_type === 'round_started'
    && Date.parse(event.created_at) <= at).length
}

export function replayStats(events: ReplayEvent[]) {
  const stats = { created: 0, moved: 0, completed: 0, sentBack: 0, deleted: 0,
    subtasksAdded: 0, subtasksCompleted: 0 }
  for (const event of events) {
    if (event.event_type === 'created') stats.created++
    else if (event.event_type === 'deleted') stats.deleted++
    else if (event.event_type === 'subtask_added') stats.subtasksAdded++
    else if (event.event_type === 'subtask_completed') stats.subtasksCompleted++
    else if (['column_change', 'review_rejected', 'review_approved'].includes(event.event_type)
      && event.from_column !== event.to_column) {
      stats.moved++
      if (event.to_column === 'done') stats.completed++
      if (event.event_type === 'review_rejected') stats.sentBack++
    }
  }
  return stats
}
