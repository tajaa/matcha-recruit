import { useEffect, useState } from 'react'
import { X, Loader2, Video } from 'lucide-react'
import { getInterview, type InterviewDetail, type ScreeningAttribute } from '../../api/matchaWork'

interface Props {
  interviewId: string
  candidateName?: string
  onClose: () => void
}

// Match RecruitingPipeline palette — matcha-work canonical theme
const c = {
  bg: '#1e1e1e',
  cardBg: '#252526',
  border: '#333',
  text: '#d4d4d4',
  heading: '#e8e8e8',
  muted: '#6a737d',
  accent: '#ce9178',
  green: '#22c55e',
  amber: '#f59e0b',
}

function scoreColor(n: number): string {
  if (n >= 75) return c.green
  if (n >= 50) return c.amber
  return '#ef4444'
}

const recLabel: Record<string, { label: string; color: string }> = {
  strong_pass: { label: 'Strong pass', color: c.green },
  pass: { label: 'Pass', color: c.green },
  borderline: { label: 'Borderline', color: c.amber },
  fail: { label: 'Fail', color: '#ef4444' },
}

function Attribute({ title, attr }: { title: string; attr: ScreeningAttribute }) {
  const color = scoreColor(attr.score)
  return (
    <div
      className="mb-2 rounded-md border px-3 py-2"
      style={{ borderColor: c.border, background: c.bg }}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: c.heading }}>{title}</span>
        <span className="text-xs font-semibold" style={{ color }}>{Math.round(attr.score)}%</span>
      </div>
      {attr.evidence?.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-[11px] leading-snug" style={{ color: c.muted }}>
          {attr.evidence.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      )}
      {attr.notes && (
        <p className="mt-1 text-[11px] italic" style={{ color: c.muted }}>{attr.notes}</p>
      )}
    </div>
  )
}

export default function InterviewReviewModal({ interviewId, candidateName, onClose }: Props) {
  const [interview, setInterview] = useState<InterviewDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showTranscript, setShowTranscript] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getInterview(interviewId)
      .then((d) => { if (!cancelled) setInterview(d) })
      .catch((e) => { if (!cancelled) setError(e?.message || 'Failed to load interview') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [interviewId])

  const analysis = interview?.screening_analysis
  const rec = analysis ? recLabel[analysis.recommendation] : null
  const overallColor = analysis ? scoreColor(analysis.overall_score) : c.muted

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onClick={onClose}
    >
      <div
        className="relative my-8 w-full max-w-xl rounded-lg border"
        style={{ background: c.cardBg, borderColor: c.border, color: c.text }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between border-b px-4 py-3"
          style={{ borderColor: c.border }}
        >
          <div className="flex items-center gap-2">
            <Video size={14} style={{ color: c.accent }} />
            <div>
              <h2 className="text-sm font-semibold" style={{ color: c.heading }}>
                Interview review{candidateName ? ` — ${candidateName}` : ''}
              </h2>
              {interview?.completed_at && (
                <p className="text-[10px]" style={{ color: c.muted }}>
                  Completed {new Date(interview.completed_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 transition-colors"
            style={{ color: c.muted }}
            onMouseEnter={(e) => (e.currentTarget.style.color = c.heading)}
            onMouseLeave={(e) => (e.currentTarget.style.color = c.muted)}
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-4 py-3">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="animate-spin" size={16} style={{ color: c.muted }} />
            </div>
          )}

          {error && !loading && (
            <p className="py-3 text-xs" style={{ color: '#ef4444' }}>{error}</p>
          )}

          {!loading && !error && interview && !analysis && (
            <p className="py-3 text-xs" style={{ color: c.muted }}>
              No analysis available yet. Interview status: {interview.status}.
            </p>
          )}

          {!loading && !error && analysis && (
            <>
              <div
                className="mb-3 flex items-center gap-5 rounded-md border px-3 py-2"
                style={{ borderColor: c.border, background: c.bg }}
              >
                <div>
                  <p className="text-[9px] uppercase tracking-wider" style={{ color: c.muted }}>Overall</p>
                  <p className="text-xl font-bold" style={{ color: overallColor }}>
                    {Math.round(analysis.overall_score)}%
                  </p>
                </div>
                {rec && (
                  <div>
                    <p className="text-[9px] uppercase tracking-wider" style={{ color: c.muted }}>Recommendation</p>
                    <p className="text-xs font-semibold" style={{ color: rec.color }}>{rec.label}</p>
                  </div>
                )}
              </div>

              <div className="mb-3">
                <p className="mb-1 text-[9px] font-medium uppercase tracking-wider" style={{ color: c.muted }}>
                  Summary
                </p>
                <p className="text-xs leading-relaxed" style={{ color: c.text }}>{analysis.summary}</p>
              </div>

              <div className="mb-3">
                <p className="mb-1.5 text-[9px] font-medium uppercase tracking-wider" style={{ color: c.muted }}>
                  Attributes
                </p>
                <Attribute title="Communication clarity" attr={analysis.communication_clarity} />
                <Attribute title="Engagement & energy" attr={analysis.engagement_energy} />
                <Attribute title="Critical thinking" attr={analysis.critical_thinking} />
                <Attribute title="Professionalism" attr={analysis.professionalism} />
              </div>

              {interview.transcript && (
                <div>
                  <button
                    onClick={() => setShowTranscript((v) => !v)}
                    className="mb-1.5 text-[9px] font-medium uppercase tracking-wider hover:underline"
                    style={{ color: c.accent }}
                  >
                    {showTranscript ? 'Hide transcript' : 'Show transcript'}
                  </button>
                  {showTranscript && (
                    <pre
                      className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md border p-2.5 text-[11px] leading-relaxed"
                      style={{ borderColor: c.border, background: c.bg, color: c.text }}
                    >
                      {interview.transcript}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
