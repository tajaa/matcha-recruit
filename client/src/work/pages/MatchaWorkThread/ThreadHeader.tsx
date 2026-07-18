import { Link } from 'react-router-dom'
import { ArrowLeft, Pencil, Check, X, Sun, Moon, Bot } from 'lucide-react'
import ThreadCollaborators from '../../components/panels/ThreadCollaborators'
import { MODEL_OPTIONS, THREAD_MODE_TOGGLES, formatTokens } from '../../components/panels/constants'
import { TASK_LABELS } from './constants'
import type { ThreadTheme } from './theme'
import type { ThreadController } from './useThreadController'

interface ThreadHeaderProps {
  c: ThreadController
  th: ThreadTheme
  lm: boolean
  hasRightPanel: boolean
}

export default function ThreadHeader({ c, th, lm, hasRightPanel }: ThreadHeaderProps) {
  const {
    base, editingTitle, titleDraft, setTitleDraft, handleTitleSave, setEditingTitle,
    thread, threadId, onlineUsers, mobileView, setMobileView, lightMode,
    isIndividual, hasFeature, modeValue, handleModeToggle, togglingMode,
    agentMode, setAgentMode, selectedModel, setSelectedModel, usage24h, usageTotal, toggleLightMode,
  } = c

  return (
    <div className={`flex items-center gap-3 px-4 py-3 border-b ${th.border}`}>
      <Link to={base} className={`${th.backArrow} transition-colors`}>
        <ArrowLeft size={18} />
      </Link>

      {editingTitle ? (
        <div className="flex items-center gap-2 flex-1">
          <input
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
            className={`${th.titleInput} text-sm px-2 py-2 rounded flex-1`}
            autoFocus
          />
          <button onClick={handleTitleSave} className="text-emerald-400 hover:text-emerald-300">
            <Check size={16} />
          </button>
          <button onClick={() => setEditingTitle(false)} className="text-zinc-400 hover:text-white">
            <X size={16} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <h2 className={`${th.titleText} font-medium truncate`}>{thread?.title}</h2>
          <button
            onClick={() => {
              setTitleDraft(thread?.title ?? '')
              setEditingTitle(true)
            }}
            className={`${th.editBtn} transition-colors shrink-0`}
          >
            <Pencil size={14} />
          </button>
          {threadId && (
            <ThreadCollaborators
              threadId={threadId}
              onlineUsers={onlineUsers}
              lightMode={lm}
            />
          )}
        </div>
      )}

      {thread?.task_type && (
        <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${th.badge}`}>
          {TASK_LABELS[thread.task_type] ?? thread.task_type}
        </span>
      )}

      {/* Mobile panel toggle */}
      {hasRightPanel && (
        <div className="flex md:hidden rounded overflow-hidden shrink-0" style={{ border: '1px solid' + (lightMode ? '#d4d4d8' : '#444') }}>
          <button
            onClick={() => setMobileView('chat')}
            className="px-2 py-1 text-[10px] font-medium"
            style={{ background: mobileView === 'chat' ? (lightMode ? '#22c55e' : '#ce9178') : (lightMode ? '#f4f4f5' : '#2a2d2e'), color: mobileView === 'chat' ? '#fff' : (lightMode ? '#71717a' : '#6a737d') }}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileView('panel')}
            className="px-2 py-1 text-[10px] font-medium"
            style={{ background: mobileView === 'panel' ? (lightMode ? '#22c55e' : '#ce9178') : (lightMode ? '#f4f4f5' : '#2a2d2e'), color: mobileView === 'panel' ? '#fff' : (lightMode ? '#71717a' : '#6a737d') }}
          >
            Panel
          </button>
        </div>
      )}

      {!isIndividual && THREAD_MODE_TOGGLES.filter((m) => !m.feature || hasFeature(m.feature)).map((m) => {
        const active = modeValue(m.key)
        const Icon = m.icon
        return (
          <button
            key={m.key}
            onClick={() => handleModeToggle(m.key)}
            disabled={togglingMode === m.key}
            title={active ? m.tipOn : m.tipOff}
            className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors disabled:opacity-50 ${
              active ? m.onClass : th.modeOff
            }`}
          >
            <Icon size={12} />
            {m.label}
          </button>
        )
      })}

      <button
        onClick={() => setAgentMode(!agentMode)}
        title={agentMode ? 'Agent ON — email inbox and AI drafting' : 'Agent OFF — click to open email agent'}
        className={`hidden sm:inline-flex shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
          agentMode
            ? 'text-white hover:bg-orange-500'
            : th.modeOff
        }`}
        style={agentMode ? { background: '#ce9178' } : {}}
      >
        <Bot size={12} />
        Agent
      </button>

      <select
        value={selectedModel}
        onChange={(e) => {
          setSelectedModel(e.target.value)
          localStorage.setItem('mw-model', e.target.value)
        }}
        className={`shrink-0 text-[11px] font-medium rounded-full px-2.5 py-1 appearance-none cursor-pointer transition-colors ${th.modeOff} ${
          lightMode ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-700 text-zinc-300'
        }`}
      >
        {MODEL_OPTIONS.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>

      {/* Token counter */}
      {(usage24h?.totals.total_tokens || usageTotal?.totals.total_tokens) ? (
        <div className={`hidden sm:flex items-center gap-1.5 text-[10px] font-mono ${lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
          {usage24h && usage24h.totals.total_tokens > 0 && <span>24h: {formatTokens(usage24h.totals.total_tokens)}</span>}
          {usage24h?.totals.total_tokens && usageTotal?.totals.total_tokens ? <span>|</span> : null}
          {usageTotal && usageTotal.totals.total_tokens > 0 && <span>30d: {formatTokens(usageTotal.totals.total_tokens)}</span>}
        </div>
      ) : null}

      <button
        onClick={toggleLightMode}
        title={lightMode ? 'Switch to dark mode' : 'Switch to light mode'}
        className={`shrink-0 p-1.5 rounded-full transition-colors ${th.backArrow}`}
      >
        {lightMode ? <Moon size={14} /> : <Sun size={14} />}
      </button>
    </div>
  )
}
