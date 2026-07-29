import { useEffect, useRef, useState } from 'react'
import { Wrench, Bot, Check } from 'lucide-react'
import { MODEL_OPTIONS, THREAD_MODE_TOGGLES } from '../../components/panels/constants'
import type { ThreadController } from './useThreadController'

interface ToolsMenuProps {
  c: ThreadController
}

// Replaces the old header's flat row of 9 saturated mode pills + a hand-rolled
// Agent pill + a native model <select> with one popover — the same
// NotificationSettingsMenu shell (outside-click to close) used elsewhere in
// the work surface, so this reads as one more piece of app chrome rather than
// a new pattern.
export default function ToolsMenu({ c }: ToolsMenuProps) {
  const {
    isIndividual, hasFeature, modeValue, handleModeToggle, togglingMode,
    agentMode, setAgentMode, selectedModel, setSelectedModel,
  } = c
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  const huumeActive = modeValue('huume')
  const visibleModes = isIndividual
    ? []
    : THREAD_MODE_TOGGLES.filter((m) => !m.feature || hasFeature(m.feature))
  const activeModes = visibleModes.filter((m) => modeValue(m.key))

  let triggerIcon = <Wrench size={14} />
  let triggerLabel = 'Tools'
  if (huumeActive) {
    const huume = THREAD_MODE_TOGGLES.find((m) => m.key === 'huume')!
    const HuumeIcon = huume.icon
    triggerIcon = <HuumeIcon size={14} />
    triggerLabel = 'Huume'
  } else if (activeModes.length === 1) {
    const Icon = activeModes[0].icon
    triggerIcon = <Icon size={14} />
    triggerLabel = activeModes[0].label
  } else if (activeModes.length > 1) {
    triggerLabel = `${activeModes.length} tools`
  }
  const triggerActive = huumeActive || activeModes.length > 0

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
          triggerActive
            ? 'text-w-accent border-w-accent/40 bg-w-accent/10'
            : 'text-w-dim border-w-line hover:text-w-text'
        }`}
        title="Tools & model"
      >
        {triggerIcon}
        {triggerLabel}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 rounded-lg border border-w-line bg-w-surface shadow-xl z-50 max-h-[70vh] overflow-y-auto text-xs">
          {!isIndividual && visibleModes.length > 0 && (
            <div>
              <div className="px-3 py-2 border-b border-w-line text-w-dim font-medium">
                Grounding modes
              </div>
              {visibleModes.map((m) => {
                const active = modeValue(m.key)
                const inertWhileHuume = huumeActive && m.key !== 'huume'
                const Icon = m.icon
                return (
                  <button
                    key={m.key}
                    onClick={() => handleModeToggle(m.key)}
                    disabled={togglingMode === m.key}
                    title={inertWhileHuume ? `${active ? m.tipOn : m.tipOff} — Huume is on, so this has no effect this turn.` : (active ? m.tipOn : m.tipOff)}
                    className={`w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-w-surface2/60 disabled:opacity-50 ${inertWhileHuume ? 'opacity-40' : ''}`}
                  >
                    <span className={active ? 'text-w-accent' : 'text-w-dim'}><Icon size={14} /></span>
                    <span className="flex-1 min-w-0">
                      <span className="block text-w-text">{m.label}</span>
                      <span className="block text-[11px] text-w-faint truncate">{m.desc}</span>
                    </span>
                    <span
                      className={`inline-block w-8 h-4 rounded-full relative transition-colors shrink-0 ${
                        active ? 'bg-w-accent' : 'bg-w-surface2'
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                          active ? 'translate-x-4' : 'translate-x-0.5'
                        }`}
                      />
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          <div className="border-t border-w-line">
            <button
              onClick={() => setAgentMode(!agentMode)}
              title={agentMode ? 'Agent ON — email inbox and AI drafting' : 'Agent OFF — click to open email agent'}
              className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-w-surface2/60"
            >
              <span className={agentMode ? 'text-w-accent' : 'text-w-dim'}><Bot size={14} /></span>
              <span className="flex-1 text-w-text">Email agent</span>
              <span
                className={`inline-block w-8 h-4 rounded-full relative transition-colors shrink-0 ${
                  agentMode ? 'bg-w-accent' : 'bg-w-surface2'
                }`}
              >
                <span
                  className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                    agentMode ? 'translate-x-4' : 'translate-x-0.5'
                  }`}
                />
              </span>
            </button>
          </div>

          <div className="border-t border-w-line">
            <div className="px-3 py-2 text-w-dim font-medium">Model</div>
            {MODEL_OPTIONS.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setSelectedModel(m.id)
                  localStorage.setItem('mw-model', m.id)
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-w-surface2/60"
              >
                <span className="w-3.5 shrink-0">{selectedModel === m.id && <Check size={14} className="text-w-accent" />}</span>
                <span className="text-w-text">{m.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
