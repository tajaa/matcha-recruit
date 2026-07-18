import { Check } from 'lucide-react'

// Kept as a broad string to avoid a cross-file import cycle with the Tab
// union in RecruitingPipeline. Parent casts back to its own union.
type JumpTarget = string

interface Props {
  sectionCount: number
  isFinalized: boolean
  candidateCount: number
  analyzedCount: number
  interviewsSentCount: number
  interviewedCount: number
  onJumpTo: (tab: JumpTarget) => void
}

interface Stage {
  label: string
  count?: number
  done: boolean
  tab: JumpTarget
}

const c = {
  bg: '#1a1a1a',
  border: '#2a2a2a',
  active: '#22c55e',
  done: '#22c55e',
  muted: '#555',
  mutedText: '#8b8b8b',
  heading: '#e4e4e7',
  connector: '#3a3a3a',
  doneConnector: '#22c55e',
}

/**
 * Always-visible compact progress strip shown above the tab bar of
 * RecruitingPipeline. Gives the user a single source of truth for
 * where they are in the hiring flow no matter which tab they're on.
 */
export default function PipelineProgressStrip({
  sectionCount,
  isFinalized,
  candidateCount,
  analyzedCount,
  interviewsSentCount,
  interviewedCount,
  onJumpTo,
}: Props) {
  const stages: Stage[] = [
    { label: 'Posting', count: sectionCount || undefined, done: isFinalized, tab: 'posting' },
    { label: 'Candidates', count: candidateCount || undefined, done: candidateCount > 0, tab: 'candidates' },
    { label: 'Analyzed', count: analyzedCount || undefined, done: analyzedCount > 0, tab: 'candidates' },
    { label: 'Interviews', count: interviewsSentCount || undefined, done: interviewsSentCount > 0, tab: 'interviews' },
    { label: 'Completed', count: interviewedCount || undefined, done: interviewedCount > 0, tab: 'interviews' },
  ]

  // Active stage = first non-done stage. If every stage is done, no active stage.
  const activeIdx = stages.findIndex((s) => !s.done)

  return (
    <div
      className="sticky top-0 z-10 flex items-center gap-0 px-4 py-2.5"
      style={{ background: c.bg, borderBottom: `1px solid ${c.border}` }}
    >
      {stages.map((stage, i) => {
        const isActive = i === activeIdx
        const isDone = stage.done
        const circleColor = isDone ? c.done : isActive ? c.active : c.muted
        const labelColor = isDone ? c.done : isActive ? c.heading : c.mutedText
        const isLast = i === stages.length - 1
        return (
          <div key={stage.label} className="flex items-center flex-1 min-w-0">
            <button
              onClick={() => onJumpTo(stage.tab)}
              className="flex items-center gap-2 group shrink-0"
              title={`Jump to ${stage.label}`}
            >
              <span
                className="flex items-center justify-center rounded-full text-[10px] font-bold shrink-0 transition-transform group-hover:scale-110"
                style={{
                  width: 20,
                  height: 20,
                  background: isDone ? c.done : isActive ? c.active : 'transparent',
                  border: `1.5px solid ${circleColor}`,
                  color: isDone || isActive ? '#fff' : circleColor,
                }}
              >
                {isDone ? <Check size={11} strokeWidth={3} /> : i + 1}
              </span>
              <span
                className="text-[11px] font-medium whitespace-nowrap group-hover:text-white transition-colors"
                style={{ color: labelColor }}
              >
                {stage.label}
                {stage.count != null && (
                  <span className="ml-1 text-[10px]" style={{ color: c.mutedText }}>
                    ({stage.count})
                  </span>
                )}
              </span>
            </button>
            {!isLast && (
              <div
                className="mx-2 h-px flex-1 min-w-[12px]"
                style={{ background: isDone ? c.doneConnector : c.connector }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
