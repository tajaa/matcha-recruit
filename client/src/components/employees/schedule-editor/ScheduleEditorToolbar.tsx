import { BriefcaseBusiness, CalendarDays, ChevronLeft, ChevronRight, Edit3, HelpCircle, Loader2, Save, Send, Sparkles, X } from 'lucide-react'
import type { ScheduleSaveState, } from '../../../hooks/employees/useScheduleEditor'
import type { CompanyLocation } from '../../../hooks/useLocationScope'
import LocationPicker from '../../shared/LocationPicker'
import type { ScheduleSummary } from '../../../types/employeeSchedule'

interface ScheduleEditorToolbarProps {
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
  jobsOpen: boolean
  jobsDisabled: boolean
  credentialsEnabled: boolean
  onToggleJobs(): void
  chatOpen: boolean
  huumeSelectionCount: number
  onToggleChat(): void
}

function saveLabel(state: ScheduleSaveState, lastSavedAt: Date | null): string {
  if (state === 'saving') return 'Saving draft...'
  if (state === 'error') return 'Save failed'
  if (state === 'saved' && lastSavedAt) return `Saved ${lastSavedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  return 'Draft changes autosave'
}

export default function ScheduleEditorToolbar({
  weekStart, summary, saveState, lastSavedAt, editPublished, publishing,
  locations, locationId, onChangeLocation,
  onPreviousWeek, onNextWeek, onThisWeek, onTogglePublishedEditing, onPublish, onExit, onHelp,
  jobsOpen, jobsDisabled, credentialsEnabled, onToggleJobs,
  chatOpen, huumeSelectionCount, onToggleChat,
}: ScheduleEditorToolbarProps) {
  return (
    <div className="border-b border-white/[0.06] bg-zinc-950/90 px-3 py-3 backdrop-blur md:px-5">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onExit} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-100">
          <X className="h-3.5 w-3.5" /> Exit editor
        </button>
        <button onClick={onHelp} className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-100" title="How to use the schedule editor"><HelpCircle className="h-3.5 w-3.5" /> How to use</button>
        <button onClick={onToggleJobs} disabled={jobsDisabled} className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40 ${jobsOpen ? 'border-emerald-500/50 text-emerald-300' : 'border-zinc-800 text-zinc-400 hover:text-zinc-100'}`} title={credentialsEnabled ? 'Configure location jobs and their required credentials' : 'Configure location jobs'}><BriefcaseBusiness className="h-3.5 w-3.5" /> {credentialsEnabled ? 'Jobs & credentials' : 'Jobs'}</button>
        <button onClick={onToggleChat} className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${chatOpen ? 'border-emerald-500/50 text-emerald-300' : 'border-zinc-800 text-zinc-400 hover:text-zinc-100'}`} title="Ask Huume about this schedule"><Sparkles className="h-3.5 w-3.5" /> Ask Huume</button>
        <div className="h-5 w-px bg-zinc-800" />
        <button onClick={onPreviousWeek} className="rounded-lg border border-zinc-800 p-1.5 text-zinc-400 hover:text-zinc-100" aria-label="Previous week"><ChevronLeft className="h-4 w-4" /></button>
        <button onClick={onThisWeek} className="rounded-lg border border-zinc-800 px-2.5 py-1.5 text-xs text-zinc-300 hover:text-zinc-100">This week</button>
        <button onClick={onNextWeek} className="rounded-lg border border-zinc-800 p-1.5 text-zinc-400 hover:text-zinc-100" aria-label="Next week"><ChevronRight className="h-4 w-4" /></button>
        <span className="ml-1 inline-flex items-center gap-1.5 text-xs text-zinc-500"><CalendarDays className="h-3.5 w-3.5" /> Week of {weekStart}</span>
        <LocationPicker locations={locations} value={locationId} onChange={onChangeLocation} />
        <div className="ml-auto flex items-center gap-2">
          <span className={`hidden items-center gap-1 text-[11px] sm:inline-flex ${saveState === 'error' ? 'text-red-400' : 'text-zinc-500'}`}>
            {saveState === 'saving' ? <Loader2 className="h-3 w-3 animate-spin" /> : saveState === 'saved' ? <Save className="h-3 w-3 text-emerald-400" /> : null}
            {saveLabel(saveState, lastSavedAt)}
          </span>
          <label className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
            <input type="checkbox" checked={editPublished} onChange={(event) => onTogglePublishedEditing(event.target.checked)} />
            <Edit3 className="h-3 w-3" /> Edit published
          </label>
          <button onClick={onPublish} disabled={publishing || !summary?.draft} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-40">
            {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Publish{summary?.draft ? ` (${summary.draft})` : ''}
          </button>
        </div>
      </div>
      <div className="mt-2 flex gap-3 text-[10px] uppercase tracking-widest text-zinc-600">
        <span>{summary?.total_shifts ?? 0} shifts</span>
        <span>{summary?.open_shifts ?? 0} open slots</span>
        <span>Drag to arrange</span>
        <span className={huumeSelectionCount ? 'text-emerald-400' : ''}>{huumeSelectionCount ? `${huumeSelectionCount} selected for Huume` : 'Use ✨ on a shift to give Huume context'}</span>
      </div>
    </div>
  )
}
