import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { getWeeklyReplay, type WeeklyReplay } from '../../api/matchaWork/replay'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'
import { foldReplay, pacificWeekStart, replayRoundIndex, replayStats } from '../../utils/replay'

const pacificLabel = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles', weekday: 'short', month: 'short', day: 'numeric',
  hour: 'numeric', minute: '2-digit',
})
const weekLabel = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', year: 'numeric',
})

export default function WeeklyReplayTab({ projectId }: { projectId: string }) {
  const [anchor] = useState(() => new Date())
  const [weekOffset, setWeekOffset] = useState(0)
  const [replay, setReplay] = useState<WeeklyReplay | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const weekStart = useMemo(() => pacificWeekStart(anchor, weekOffset), [anchor, weekOffset])

  useEffect(() => {
    let cancelled = false
    queueMicrotask(() => {
      if (cancelled) return
      setLoading(true)
      setError(null)
      setReplay(null)
      setIndex(0)
      setPlaying(false)
    })
    void getWeeklyReplay(projectId, weekStart).then((result) => {
      if (!cancelled) setReplay(result)
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load replay')
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [projectId, weekStart])

  useEffect(() => {
    if (!playing || !replay?.events.length) return
    const interval = window.setInterval(() => {
      setIndex((current) => {
        if (current >= replay.events.length) {
          setPlaying(false)
          return current
        }
        return current + 1
      })
    }, Math.max(320, 22_000 / replay.events.length))
    return () => window.clearInterval(interval)
  }, [playing, replay])

  const cards = useMemo(() => replay ? foldReplay(replay, index) : [], [replay, index])
  const applied = replay?.events.slice(0, index) ?? []
  const stats = replayStats(applied)
  const latest = applied.at(-1)
  const moment = latest?.created_at ?? replay?.week_start ?? weekStart

  return <section className="flex min-h-0 flex-1 flex-col bg-w-bg text-w-text" aria-label="Weekly work replay">
    <div className="flex flex-wrap items-center gap-3 border-b border-w-line px-4 py-3">
      <button onClick={() => setWeekOffset((value) => value - 1)} aria-label="Previous week" className="rounded p-1 hover:bg-w-surface2"><ChevronLeft size={17} /></button>
      <strong className="min-w-28 text-sm">Week of {weekLabel.format(new Date(weekStart))}</strong>
      <button onClick={() => setWeekOffset((value) => value + 1)} disabled={weekOffset >= 0} aria-label="Next week" className="rounded p-1 hover:bg-w-surface2 disabled:opacity-40"><ChevronRight size={17} /></button>
      <span className="ml-auto text-xs text-w-dim">{pacificLabel.format(new Date(moment))} Pacific</span>
    </div>
    {loading && <p className="p-5 text-sm text-w-dim">Loading history…</p>}
    {error && <p className="p-5 text-sm text-red-400" role="alert">{error}</p>}
    {!loading && replay && <>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-b border-w-line px-4 py-2 text-xs text-w-dim">
        <span>{stats.created} created</span><span>{stats.moved} moved</span><span>{stats.completed} completed</span>
        <span>{stats.sentBack} sent back</span><span>{stats.deleted} deleted</span>
        <span>{stats.subtasksAdded} subtasks added</span><span>{stats.subtasksCompleted} subtasks completed</span>
      </div>
      {replay.events.length === 0 && cards.length === 0 ? <p className="p-5 text-sm text-w-dim">No activity this week.</p> : <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto p-4">
        {KANBAN_COLUMNS.map((column) => <div key={column.key} className="min-w-[190px] flex-1 rounded-lg border border-w-line bg-w-surface p-2">
          <h3 className="mb-2 text-xs font-semibold text-w-dim">{column.label} <span className="font-normal">{cards.filter((card) => card.column === column.key && !card.is_deleted).length}</span></h3>
          <div className="space-y-2">{cards.filter((card) => card.column === column.key).map((card) => <div key={card.task_id} className={`rounded border border-w-line bg-w-bg p-2 text-xs ${card.is_deleted ? 'opacity-40 line-through' : ''}`}>
            <span className="font-medium">{card.title}</span>
            {card.assignee_name && <p className="mt-1 text-w-dim">{card.assignee_name}</p>}
            {replayRoundIndex(applied, card.task_id, moment) > 1 && <p className="mt-1 text-w-dim">Round {replayRoundIndex(applied, card.task_id, moment)}</p>}
          </div>)}</div>
        </div>)}
      </div>}
      <div className="flex items-center gap-3 border-t border-w-line px-4 py-3">
        <button onClick={() => { if (index >= replay.events.length) setIndex(0); setPlaying((value) => !value) }} disabled={!replay.events.length} aria-label={playing ? 'Pause replay' : 'Play replay'} className="rounded border border-w-line p-2 disabled:opacity-40">{playing ? <Pause size={15} /> : <Play size={15} />}</button>
        <input type="range" min={0} max={replay.events.length} value={index} onChange={(event) => { setPlaying(false); setIndex(Number(event.target.value)) }} aria-label="Replay position" className="min-w-0 flex-1 accent-w-accent" />
        <span className="text-xs tabular-nums text-w-dim">{index} / {replay.events.length}</span>
      </div>
      {latest && <p className="border-t border-w-line px-4 py-1.5 text-xs text-w-dim">{latest.actor_name || 'Someone'} · {latest.event_type.replaceAll('_', ' ')} · {latest.title}</p>}
    </>}
  </section>
}
