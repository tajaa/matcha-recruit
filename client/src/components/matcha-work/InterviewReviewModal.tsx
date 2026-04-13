import { useEffect, useState } from 'react'
import { X, Loader2, Video } from 'lucide-react'
import { getInterview, type InterviewDetail, type ScreeningAttribute } from '../../api/matchaWork'

interface Props {
  interviewId: string
  candidateName?: string
  onClose: () => void
}

const c = {
  bg: '#1e1e1e', cardBg: '#252526', border: '#333', text: '#d4d4d4',
  heading: '#e8e8e8', muted: '#8a8a8a', accent: '#ce9178', hoverBg: '#2a2d2e',
}

const recLabel: Record<string, { label: string; color: string }> = {
  strong_pass: { label: 'Strong pass', color: '#22c55e' },
  pass: { label: 'Pass', color: '#4ade80' },
  borderline: { label: 'Borderline', color: '#f59e0b' },
  fail: { label: 'Fail', color: '#ef4444' },
}

function Attribute({ title, attr }: { title: string; attr: ScreeningAttribute }) {
  return (
    <div className="mb-3 rounded-lg border p-3" style={{ borderColor: c.border, background: c.bg }}>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-sm font-medium" style={{ color: c.heading }}>{title}</span>
        <span className="text-sm font-semibold" style={{ color: '#60a5fa' }}>{Math.round(attr.score)}%</span>
      </div>
      {attr.evidence?.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-xs" style={{ color: c.muted }}>
          {attr.evidence.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      )}
      {attr.notes && <p className="mt-1 text-xs italic" style={{ color: c.muted }}>{attr.notes}</p>}
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="relative my-8 w-full max-w-2xl rounded-xl border shadow-xl"
        style={{ background: c.cardBg, borderColor: c.border, color: c.text }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b p-4" style={{ borderColor: c.border }}>
          <div className="flex items-center gap-2">
            <Video size={16} style={{ color: '#60a5fa' }} />
            <div>
              <h2 className="text-base font-semibold" style={{ color: c.heading }}>
                Interview review{candidateName ? ` — ${candidateName}` : ''}
              </h2>
              {interview?.completed_at && (
                <p className="text-xs" style={{ color: c.muted }}>
                  Completed {new Date(interview.completed_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 hover:bg-white/10"
            style={{ color: c.muted }}
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4">
          {loading && (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="animate-spin" size={20} style={{ color: c.muted }} />
            </div>
          )}

          {error && !loading && (
            <p className="py-4 text-sm" style={{ color: '#ef4444' }}>{error}</p>
          )}

          {!loading && !error && interview && !analysis && (
            <p className="py-4 text-sm" style={{ color: c.muted }}>
              No analysis available yet. Interview status: {interview.status}.
            </p>
          )}

          {!loading && !error && analysis && (
            <>
              <div className="mb-4 flex items-center gap-4 rounded-lg border p-3" style={{ borderColor: c.border, background: c.bg }}>
                <div>
                  <p className="text-[10px] uppercase tracking-wide" style={{ color: c.muted }}>Overall</p>
                  <p className="text-2xl font-bold" style={{ color: '#60a5fa' }}>{Math.round(analysis.overall_score)}%</p>
                </div>
                {rec && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide" style={{ color: c.muted }}>Recommendation</p>
                    <p className="text-sm font-semibold" style={{ color: rec.color }}>{rec.label}</p>
                  </div>
                )}
              </div>

              <div className="mb-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide" style={{ color: c.muted }}>Summary</p>
                <p className="text-sm" style={{ color: c.text }}>{analysis.summary}</p>
              </div>

              <div className="mb-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide" style={{ color: c.muted }}>Attributes</p>
                <Attribute title="Communication clarity" attr={analysis.communication_clarity} />
                <Attribute title="Engagement & energy" attr={analysis.engagement_energy} />
                <Attribute title="Critical thinking" attr={analysis.critical_thinking} />
                <Attribute title="Professionalism" attr={analysis.professionalism} />
              </div>

              {interview.transcript && (
                <div>
                  <button
                    onClick={() => setShowTranscript((v) => !v)}
                    className="mb-2 text-xs font-medium uppercase tracking-wide hover:underline"
                    style={{ color: '#60a5fa' }}
                  >
                    {showTranscript ? 'Hide transcript' : 'Show transcript'}
                  </button>
                  {showTranscript && (
                    <pre
                      className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border p-3 text-xs"
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
