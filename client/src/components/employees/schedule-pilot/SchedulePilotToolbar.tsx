import { CalendarDays, ChevronLeft, ChevronRight, Edit3, HelpCircle, LayoutGrid, ListChecks, Loader2, MessageSquareText, PanelLeft, Save, Send, Sparkles, X } from 'lucide-react'
import type { ScheduleSaveState } from '../../../hooks/employees/useScheduleEditor'
import type { CompanyLocation } from '../../../hooks/useLocationScope'
import LocationPicker from '../../shared/LocationPicker'
import type { ScheduleSummary } from '../../../types/employeeSchedule'
import { weekRangeLabel } from './weekLabel'

export type CenterView = 'board' | 'review'

interface SchedulePilotToolbarProps {
  weekStart: string
  summary: ScheduleSummary | null
  saveState: ScheduleSaveState
  lastSavedAt: Date | null
  editPublished: boolean
  publishing: boolean
  locations: CompanyLocation[]
  locationId: string
  onChangeLocation(id: string): void
  onPreviousWeek(): void
  onNextWeek(): void
  onThisWeek(): void
  onTogglePublishedEditing(value: boolean): void
  onPublish(): void
  onExit(): void
  onHelp(): void
  centerView: CenterView
  onSetCenterView(view: CenterView): void
  /** Something is staged or a scenario is selected — the Review tab has content. */
  reviewReady: boolean
  railOpen: boolean
  onToggleRail(): void
  threadOpen: boolean
  onToggleThread(): void
  huumeSelectionCount: number
  /** False when the plan has no Huume: its toggle and hints are left out
   *  rather than pointing at a panel that can only answer with an error. */
  huumeEnabled?: boolean
  /** Rendered beside the location picker — the page's store actions. */
  storeActions?: React.ReactNode
  autopilot?: { visible: boolean; running: boolean; onOpen(): void }
}

function saveLabel(state: ScheduleSaveState, lastSavedAt: Date | null): string {
  if (state === 'saving') return 'Saving draft...'
  if (state === 'error') return 'Save failed'
  if (state === 'saved' && lastSavedAt) return `Saved ${lastSavedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  return 'Draft changes autosave'
}

const divider = <div className="hidden h-5 w-px bg-zinc-800 sm:block" />

/** Two rows, each one job. Top: where and when (store, week) and the one
 *  thing that leaves the page, Publish. Bottom: how you're working (Huume,
 *  inputs, board or review), what's on the board, and the helpers. */
export default function SchedulePilotToolbar({
  weekStart, summary, saveState, lastSavedAt, editPublished, publishing,
  locations, locationId, onChangeLocation,
  onPreviousWeek, onNextWeek, onThisWeek, onTogglePublishedEditing, onPublish, onExit, onHelp,
  centerView, onSetCenterView, reviewReady, railOpen, onToggleRail, threadOpen, onToggleThread, huumeSelectionCount, autopilot,
  huumeEnabled = true, storeActions,
}: SchedulePilotToolbarProps) {
  const paneButton = (active: boolean) => `hidden items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs lg:inline-flex ${active ? 'border-emerald-500/50 bg-emerald-500/[0.06] text-emerald-300' : 'border-zinc-800 text-zinc-400 hover:text-zinc-100'}`
  const iconButton = 'rounded-lg border border-zinc-800 p-1.5 text-zinc-400 hover:text-zinc-100'
  const total = summary?.total_shifts ?? 0
  const open = summary?.open_shifts ?? 0
  return (
    <div className="shrink-0 border-b border-white/[0.06] bg-zinc-950/90 px-3 py-2 backdrop-blur md:px-4">
      {/* Where and when */}
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onExit} className={iconButton} aria-label="Exit" title="Exit to the schedule"><X className="h-4 w-4" /></button>
        <span className="hidden text-sm font-semibold tracking-tight text-zinc-100 md:inline">Schedule Pilot</span>
        {divider}
        <div className="flex items-center gap-1.5" role="group" aria-label="Store">
          <LocationPicker compact locations={locations} value={locationId} onChange={onChangeLocation} />
          {storeActions}
        </div>
        {divider}
        <div className="flex items-center gap-1" role="group" aria-label="Week">
          <button onClick={onPreviousWeek} className={iconButton} aria-label="Previous week"><ChevronLeft className="h-4 w-4" /></button>
          <span className="inline-flex min-w-[9.5rem] items-center justify-center gap-1.5 px-1 text-xs font-medium text-zinc-200" title={`Week of ${weekStart}`}>
            <CalendarDays className="h-3.5 w-3.5 text-zinc-500" /> {weekRangeLabel(weekStart)}
          </span>
          <button onClick={onNextWeek} className={iconButton} aria-label="Next week"><ChevronRight className="h-4 w-4" /></button>
          <button onClick={onThisWeek} className="rounded-lg px-2 py-1.5 text-[11px] text-zinc-500 hover:text-zinc-100">This week</button>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className={`hidden items-center gap-1 text-[11px] sm:inline-flex ${saveState === 'error' ? 'text-red-400' : 'text-zinc-500'}`}>
            {saveState === 'saving' ? <Loader2 className="h-3 w-3 animate-spin" /> : saveState === 'saved' ? <Save className="h-3 w-3 text-emerald-400" /> : null}
            {saveLabel(saveState, lastSavedAt)}
          </span>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-zinc-400" title="Let changes reach shifts that are already published">
            <input type="checkbox" className="accent-emerald-500" checked={editPublished} onChange={(event) => onTogglePublishedEditing(event.target.checked)} />
            <Edit3 className="h-3 w-3" /> Edit published
          </label>
          <button onClick={onPublish} disabled={publishing || !summary?.draft} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-40">
            {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Publish{summary?.draft ? ` (${summary.draft})` : ''}
          </button>
        </div>
      </div>

      {/* How you're working */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {huumeEnabled && <button onClick={onToggleThread} aria-pressed={threadOpen} className={paneButton(threadOpen)} title="Show or hide the Huume thread"><MessageSquareText className="h-3.5 w-3.5" /> Huume</button>}
        <button onClick={onToggleRail} aria-pressed={railOpen} className={paneButton(railOpen)} title="People, open seats and policy"><PanelLeft className="h-3.5 w-3.5" /> Inputs</button>
        <div className="inline-flex overflow-hidden rounded-lg border border-white/[0.08] bg-zinc-900" role="tablist" aria-label="Center pane">
          <button role="tab" aria-selected={centerView === 'board'} onClick={() => onSetCenterView('board')} className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs ${centerView === 'board' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-200'}`}><LayoutGrid className="h-3.5 w-3.5" /> Board</button>
          <button role="tab" aria-selected={centerView === 'review'} onClick={() => onSetCenterView('review')} className={`inline-flex items-center gap-1.5 border-l border-white/[0.04] px-3 py-1.5 text-xs ${centerView === 'review' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-200'}`}>
            <ListChecks className="h-3.5 w-3.5" /> Review
            {reviewReady && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-label="Review has content" />}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-zinc-500" aria-label="This week">
          <span className="rounded-md bg-white/[0.04] px-2 py-1">{total} {total === 1 ? 'shift' : 'shifts'}</span>
          <span className={`rounded-md px-2 py-1 ${open ? 'bg-amber-500/10 text-amber-300' : 'bg-white/[0.04]'}`} title="Shifts with a seat nobody fills yet">{open} unfilled</span>
          {huumeEnabled && huumeSelectionCount > 0 && (
            <span className="rounded-md bg-emerald-500/10 px-2 py-1 text-emerald-300">{huumeSelectionCount} selected for Huume</span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {autopilot?.visible && (
            <button type="button" onClick={autopilot.onOpen} disabled={autopilot.running} title="Check setup and prepare a reviewable week" className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/35 bg-emerald-500/[0.07] px-2.5 py-1.5 text-xs text-emerald-200 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40">
              {autopilot.running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Build with Autopilot
            </button>
          )}
          <button onClick={onHelp} className={iconButton} aria-label="How to use" title="How to use the Schedule Pilot — tip: use ✨ on a shift to give Huume context"><HelpCircle className="h-4 w-4" /></button>
        </div>
      </div>
    </div>
  )
}
