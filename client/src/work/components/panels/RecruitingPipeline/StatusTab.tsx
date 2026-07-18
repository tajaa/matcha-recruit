import { c } from './constants'

interface Props {
  createdAt: string
  sectionCount: number
  isFinalized: boolean
  candidateCount: number
  analyzedCount: number
  interviewSentCount: number
  interviewedCount: number
  placeholderCount: number
}

type Stage = { label: string; done: boolean; active: boolean; detail?: string }

export default function StatusTab({
  createdAt, sectionCount, isFinalized, candidateCount, analyzedCount,
  interviewSentCount, interviewedCount, placeholderCount,
}: Props) {
  const created = new Date(createdAt)
  const now = new Date()
  const daysOpen = Math.max(1, Math.ceil((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24)))

  const stages: Stage[] = [
    { label: 'Draft Posting', done: sectionCount > 0, active: !isFinalized && sectionCount === 0, detail: sectionCount > 0 ? `${sectionCount} section${sectionCount !== 1 ? 's' : ''}` : undefined },
    { label: 'Finalize Posting', done: isFinalized, active: sectionCount > 0 && !isFinalized, detail: isFinalized ? 'Complete' : (placeholderCount > 0 ? `${placeholderCount} fields to fill` : undefined) },
    { label: 'Upload Resumes', done: candidateCount > 0, active: isFinalized && candidateCount === 0, detail: candidateCount > 0 ? `${candidateCount} candidate${candidateCount !== 1 ? 's' : ''}` : undefined },
    { label: 'Analyze Candidates', done: analyzedCount > 0, active: candidateCount > 0 && analyzedCount === 0, detail: analyzedCount > 0 ? `${analyzedCount} ranked` : undefined },
    { label: 'Send Interviews', done: interviewSentCount > 0, active: analyzedCount > 0 && interviewSentCount === 0, detail: interviewSentCount > 0 ? `${interviewSentCount} sent` : undefined },
    { label: 'Interviews Completed', done: interviewedCount > 0, active: interviewSentCount > 0 && interviewedCount === 0, detail: interviewedCount > 0 ? `${interviewedCount} done` : undefined },
    { label: 'Offer Sent', done: false, active: interviewedCount > 0, detail: undefined },
    { label: 'Position Filled', done: false, active: false, detail: undefined },
  ]

  const currentStage = stages.findIndex((s) => s.active) + 1 || stages.filter((s) => s.done).length

  return (
    <div className="p-4 space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Days Open', value: daysOpen },
          { label: 'Candidates', value: candidateCount },
          { label: 'Interviewed', value: interviewedCount },
        ].map((stat) => (
          <div key={stat.label} className="rounded-lg p-3 text-center" style={{ background: c.cardBg, border: `1px solid ${c.border}` }}>
            <p className="text-lg font-bold" style={{ color: c.heading }}>{stat.value}</p>
            <p className="text-[10px]" style={{ color: c.muted }}>{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Pipeline stages */}
      <div>
        <p className="text-[10px] font-medium mb-2" style={{ color: c.muted }}>PIPELINE STAGE ({currentStage}/{stages.length})</p>
        <div className="space-y-1">
          {stages.map((stage, i) => (
            <div
              key={i}
              className="flex items-center gap-2.5 px-3 py-2 rounded"
              style={{
                background: stage.active ? `${c.accent}15` : stage.done ? `${c.green}10` : 'transparent',
                border: stage.active ? `1px solid ${c.accent}40` : '1px solid transparent',
              }}
            >
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[10px] font-bold"
                style={{
                  background: stage.done ? c.green : stage.active ? c.accent : c.border,
                  color: stage.done || stage.active ? '#fff' : c.muted,
                }}
              >
                {stage.done ? '✓' : i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium" style={{ color: stage.done ? c.green : stage.active ? c.accent : c.muted }}>
                  {stage.label}
                </p>
              </div>
              {stage.detail && (
                <span className="text-[10px] shrink-0" style={{ color: c.muted }}>{stage.detail}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
