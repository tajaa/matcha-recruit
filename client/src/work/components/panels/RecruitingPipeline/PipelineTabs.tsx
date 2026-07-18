import { Search, Loader2, Send, Video, RefreshCw } from 'lucide-react'
import type { ResumeCandidate } from '../../../types'
import { c } from './constants'
import type { Tab } from './types'

interface Props {
  tabs: { key: Tab; label: string; count?: number }[]
  tab: Tab
  setTab: (tab: Tab) => void
  tabUnlocked: Record<Tab, boolean>
  saving: boolean
  showSaved: boolean
  hasInterviews: boolean
  onSyncInterviews?: () => Promise<void>
  candidates: ResumeCandidate[]
  onAnalyzeCandidates?: () => Promise<void>
  analyzing: boolean
  handleAnalyze: () => Promise<void>
  selectableIds: string[]
  onSendInterviews?: (candidateIds: string[], positionTitle?: string) => Promise<void>
  toggleSelectAll: () => void
  selectedIds: Set<string>
  showPositionPrompt: boolean
  setShowPositionPrompt: (v: boolean) => void
  sendingInterviews: boolean
  positionInput: string
  setPositionInput: (v: string) => void
  handleSendInterviews: () => Promise<void>
}

export default function PipelineTabs({
  tabs, tab, setTab, tabUnlocked, saving, showSaved, hasInterviews, onSyncInterviews,
  candidates, onAnalyzeCandidates, analyzing, handleAnalyze, selectableIds, onSendInterviews,
  toggleSelectAll, selectedIds, showPositionPrompt, setShowPositionPrompt, sendingInterviews,
  positionInput, setPositionInput, handleSendInterviews,
}: Props) {
  return (
    <>
      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-3 py-2 overflow-x-auto" style={{ borderBottom: `1px solid ${c.border}` }}>
        {tabs.map((t) => {
          const locked = !tabUnlocked[t.key]
          return (
            <button
              key={t.key}
              onClick={() => { if (!locked) setTab(t.key) }}
              className="px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap"
              style={{
                color: locked ? `${c.muted}60` : tab === t.key ? c.heading : c.muted,
                background: tab === t.key && !locked ? c.hoverBg : 'transparent',
                cursor: locked ? 'not-allowed' : 'pointer',
                opacity: locked ? 0.5 : 1,
              }}
              title={locked ? 'Complete previous steps first' : undefined}
            >
              {t.label}
              {t.count != null && t.count > 0 && (
                <span className="ml-1 text-[9px] px-1 py-0.5 rounded-full" style={{ background: c.border, color: c.muted }}>
                  {t.count}
                </span>
              )}
            </button>
          )
        })}
        <div className="flex items-center gap-1.5 ml-auto">
          {saving && <Loader2 size={10} className="animate-spin" style={{ color: c.muted }} />}
          {!saving && showSaved && <span className="text-[10px] font-medium" style={{ color: c.green }}>Saved</span>}
          {hasInterviews && onSyncInterviews && (
            <button
              onClick={onSyncInterviews}
              title="Refresh interview statuses"
              className="flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded transition-colors hover:bg-zinc-800"
              style={{ color: c.muted }}
            >
              <RefreshCw size={10} />
              Refresh
            </button>
          )}
          {tab === 'candidates' && candidates.length > 0 && onAnalyzeCandidates && (
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
              style={{ background: c.accent, color: '#fff' }}
            >
              {analyzing ? <Loader2 size={10} className="animate-spin" /> : <Search size={10} />}
              {analyzing ? 'Analyzing...' : 'Analyze'}
            </button>
          )}
          {tab === 'candidates' && selectableIds.length > 0 && onSendInterviews && (
            <button
              onClick={toggleSelectAll}
              className="text-[10px] font-medium px-2 py-1 rounded transition-colors"
              style={{ color: c.muted }}
            >
              {selectedIds.size >= selectableIds.length ? 'Clear' : 'Select All'}
            </button>
          )}
          {selectedIds.size > 0 && onSendInterviews && !showPositionPrompt && (
            <button
              onClick={() => setShowPositionPrompt(true)}
              disabled={sendingInterviews}
              className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
              style={{ background: c.green, color: '#fff' }}
            >
              <Video size={10} />
              Interview ({selectedIds.size})
            </button>
          )}
        </div>
      </div>
      {/* Position title prompt */}
      {showPositionPrompt && (
        <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: `1px solid ${c.border}` }}>
          <input
            value={positionInput}
            onChange={(e) => setPositionInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSendInterviews() }}
            placeholder="Position title (e.g. Senior Engineer)"
            autoFocus
            className="flex-1 text-xs rounded px-2.5 py-1.5 border focus:outline-none"
            style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
          />
          <button
            onClick={handleSendInterviews}
            disabled={sendingInterviews}
            className="p-1.5 rounded transition-colors disabled:opacity-40"
            style={{ background: c.green, color: '#fff' }}
          >
            {sendingInterviews ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          </button>
          <button
            onClick={() => { setShowPositionPrompt(false); setPositionInput('') }}
            className="text-[10px]"
            style={{ color: c.muted }}
          >
            Cancel
          </button>
        </div>
      )}
    </>
  )
}
