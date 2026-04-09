import { useState, useEffect, useRef, useCallback } from 'react'
import { Mic, MicOff, Square, Play, Loader2, Globe, ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import { useVoiceSession } from '../../hooks/useVoiceSession'
import { startTutorSession, getTutorStatus, checkUtterance, type TutorStartResponse, type TutorAnalysis, type UtteranceError } from '../../api/matchaWork'

interface LanguageTutorPanelProps {
  threadId: string
  lightMode: boolean
  currentState: Record<string, unknown> | null
  onStateUpdate?: () => void
}

type PanelPhase = 'setup' | 'active' | 'analyzing' | 'results'

interface Transcript {
  role: 'user' | 'assistant'
  text: string
}

const DURATIONS = [
  { value: 0.33, label: '20s test' },
  { value: 2, label: '2 min' },
  { value: 5, label: '5 min' },
  { value: 8, label: '8 min' },
] as const

const CEFR_COLORS: Record<string, string> = {
  A1: '#ef4444', A2: '#f97316', B1: '#eab308', B2: '#22c55e', C1: '#3b82f6', C2: '#8b5cf6',
}

function ScoreBar({ score, max = 10, lightMode }: { score: number; max?: number; lightMode: boolean }) {
  const pct = Math.min(100, (score / max) * 100)
  return (
    <div style={{ height: 6, borderRadius: 3, background: lightMode ? '#e5e7eb' : '#374151', overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${pct}%`, borderRadius: 3, background: pct > 70 ? '#22c55e' : pct > 40 ? '#eab308' : '#ef4444', transition: 'width 0.5s' }} />
    </div>
  )
}

export default function LanguageTutorPanel({ threadId, lightMode, currentState, onStateUpdate }: LanguageTutorPanelProps) {
  // Recover state from current_state if session already exists
  const tutorState = (currentState?.language_tutor as { interview_id?: string; language?: string; status?: string; message_saved?: boolean }) ?? null

  const [phase, setPhase] = useState<PanelPhase>(() => {
    if (!tutorState) return 'setup'
    if (tutorState.status === 'completed' || tutorState.message_saved) return 'results'
    if (tutorState.status === 'active') return 'setup' // WS disconnected, let user restart
    return 'setup'
  })
  const [language, setLanguage] = useState<'en' | 'es'>(
    (tutorState?.language as 'en' | 'es') ?? 'en'
  )
  const [duration, setDuration] = useState(5)
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [sessionInfo, setSessionInfo] = useState<TutorStartResponse | null>(null)
  const [analysis, setAnalysis] = useState<TutorAnalysis | null>(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['proficiency', 'grammar']))
  const [inlineErrors, setInlineErrors] = useState<Map<number, UtteranceError[]>>(new Map())
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const checkedRef = useRef<Set<string>>(new Set()) // track which utterances we've checked

  const bg = lightMode ? '#ffffff' : '#1e1e1e'
  const fg = lightMode ? '#111827' : '#e5e7eb'
  const muted = lightMode ? '#6b7280' : '#9ca3af'
  const cardBg = lightMode ? '#f3f4f6' : '#252526'
  const border = lightMode ? '#e5e7eb' : '#333'

  // Scroll transcripts
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts])

  // Fire error check for a completed user utterance
  const fireCheck = useCallback((idx: number, utterance: string) => {
    const key = `${idx}:${utterance}`
    if (checkedRef.current.has(key)) return
    checkedRef.current.add(key)
    checkUtterance(threadId, utterance, language).then(res => {
      if (res.errors.length > 0) {
        setInlineErrors(m => new Map(m).set(idx, res.errors))
      }
    }).catch(() => {})
  }, [threadId, language])

  const handleTranscript = useCallback((role: 'user' | 'assistant', text: string) => {
    if (!text.trim()) return
    setTranscripts(prev => {
      // Merge consecutive same-role entries
      if (prev.length > 0 && prev[prev.length - 1].role === role) {
        return [...prev.slice(0, -1), { role, text: prev[prev.length - 1].text + ' ' + text }]
      }
      return [...prev, { role, text }]
    })
  }, [])

  // Check user utterances when assistant starts speaking (meaning user just finished)
  useEffect(() => {
    if (transcripts.length < 2) return
    const last = transcripts[transcripts.length - 1]
    const prev = transcripts[transcripts.length - 2]
    if (last.role === 'assistant' && prev.role === 'user') {
      fireCheck(transcripts.length - 2, prev.text)
    }
  }, [transcripts, fireCheck])

  // Also check final user utterance when session ends
  const prevPhaseRef = useRef(phase)
  useEffect(() => {
    if (prevPhaseRef.current === 'active' && phase === 'analyzing' && transcripts.length > 0) {
      const last = transcripts[transcripts.length - 1]
      if (last.role === 'user') {
        fireCheck(transcripts.length - 1, last.text)
      }
    }
    prevPhaseRef.current = phase
  }, [phase, transcripts, fireCheck])

  const handleSessionEnded = useCallback(() => {
    if (pollRef.current) return // already polling, don't double-fire
    setPhase('analyzing')
    // Start polling for analysis
    pollRef.current = setInterval(async () => {
      try {
        const res = await getTutorStatus(threadId)
        if (res.status === 'completed' && res.tutor_analysis) {
          setAnalysis(res.tutor_analysis)
          setPhase('results')
          onStateUpdate?.()
          if (pollRef.current) clearInterval(pollRef.current)
        } else if (res.status === 'cancelled') {
          setPhase('setup')
          if (pollRef.current) clearInterval(pollRef.current)
        }
      } catch {
        // keep polling
      }
    }, 2000)
  }, [threadId, onStateUpdate])

  // Load existing analysis on mount if phase is results
  useEffect(() => {
    if (phase === 'results' && !analysis && tutorState?.interview_id) {
      getTutorStatus(threadId).then(res => {
        if (res.tutor_analysis) setAnalysis(res.tutor_analysis)
      }).catch(() => {})
    }
  }, [phase, analysis, threadId, tutorState])

  // Cleanup poll on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const voice = useVoiceSession(
    sessionInfo
      ? {
          websocketUrl: sessionInfo.websocket_url,
          wsAuthToken: sessionInfo.ws_auth_token,
          maxDurationSeconds: sessionInfo.max_session_duration_seconds,
          onTranscript: handleTranscript,
          onSessionEnded: handleSessionEnded,
        }
      : null
  )

  // Auto-start voice when session info is ready
  const voiceStartRef = useRef(voice.start)
  voiceStartRef.current = voice.start
  const voiceStatus = voice.status
  useEffect(() => {
    if (sessionInfo && voiceStatus === 'idle') {
      voiceStartRef.current()
    }
  }, [sessionInfo, voiceStatus])

  const handleStart = async () => {
    setError('')
    setStarting(true)
    setTranscripts([])
    try {
      const res = await startTutorSession(threadId, language, duration)
      setSessionInfo(res)
      setPhase('active')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session')
    } finally {
      setStarting(false)
    }
  }

  const handleNewSession = () => {
    setPhase('setup')
    setSessionInfo(null)
    setAnalysis(null)
    setTranscripts([])
    setInlineErrors(new Map())
    checkedRef.current.clear()
    setError('')
  }

  const toggleSection = (key: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  // ── Setup Phase ──
  if (phase === 'setup') {
    return (
      <div style={{ height: '100%', background: bg, color: fg, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, gap: 24 }}>
        <Globe size={48} style={{ color: muted, opacity: 0.6 }} />
        <div style={{ fontSize: 20, fontWeight: 600 }}>Language Practice</div>
        <div style={{ color: muted, fontSize: 13, textAlign: 'center', maxWidth: 280 }}>
          Practice conversational {language === 'en' ? 'English' : 'Spanish'} with an AI tutor.
          Get real-time feedback and a detailed analysis when you're done.
        </div>

        {/* Language toggle */}
        <div style={{ display: 'flex', gap: 8 }}>
          {(['en', 'es'] as const).map(l => (
            <button
              key={l}
              onClick={() => setLanguage(l)}
              style={{
                padding: '8px 20px', borderRadius: 8, border: `1px solid ${border}`,
                background: language === l ? '#3b82f6' : cardBg,
                color: language === l ? '#fff' : fg,
                cursor: 'pointer', fontSize: 14, fontWeight: 500,
              }}
            >
              {l === 'en' ? 'English' : 'Espa\u00f1ol'}
            </button>
          ))}
        </div>

        {/* Duration */}
        <div style={{ display: 'flex', gap: 8 }}>
          {DURATIONS.map(d => (
            <button
              key={d.value}
              onClick={() => setDuration(d.value)}
              style={{
                padding: '6px 16px', borderRadius: 8, border: `1px solid ${border}`,
                background: duration === d.value ? '#3b82f6' : cardBg,
                color: duration === d.value ? '#fff' : fg,
                cursor: 'pointer', fontSize: 13,
              }}
            >
              {d.label}
            </button>
          ))}
        </div>

        {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

        <button
          onClick={handleStart}
          disabled={starting}
          style={{
            padding: '12px 32px', borderRadius: 12, border: 'none',
            background: '#22c55e', color: '#fff', cursor: starting ? 'wait' : 'pointer',
            fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8,
            opacity: starting ? 0.7 : 1,
          }}
        >
          {starting ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
          {starting ? 'Connecting...' : 'Start Session'}
        </button>
      </div>
    )
  }

  // ── Active Phase ──
  if (phase === 'active') {
    const maxSec = sessionInfo?.max_session_duration_seconds ?? duration * 60
    return (
      <div style={{ height: '100%', background: bg, color: fg, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: voice.status === 'active' ? '#22c55e' : '#eab308', animation: voice.status === 'active' ? 'pulse 2s infinite' : undefined }} />
            <span style={{ fontSize: 13, fontWeight: 500 }}>
              {voice.status === 'connecting' ? 'Connecting...' : voice.status === 'active' ? (language === 'en' ? 'English Practice' : 'Pr\u00e1ctica de Espa\u00f1ol') : 'Ending...'}
            </span>
          </div>
          <span style={{ fontSize: 13, color: muted, fontFamily: 'monospace' }}>
            {formatTime(voice.elapsedSeconds)} / {formatTime(maxSec)}
          </span>
        </div>

        {/* Transcript area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {transcripts.length === 0 && (
            <div style={{ color: muted, fontSize: 13, textAlign: 'center', marginTop: 40 }}>
              {voice.status === 'connecting' ? 'Connecting to tutor...' : 'Listening... Start speaking!'}
            </div>
          )}
          {transcripts.map((t, i) => {
            const errors = inlineErrors.get(i)
            return (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: t.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <span style={{ fontSize: 10, color: muted, marginBottom: 2 }}>{t.role === 'user' ? 'You' : 'Tutor'}</span>
                <div style={{
                  padding: '8px 12px', borderRadius: 12, maxWidth: '85%', fontSize: 14, lineHeight: 1.5,
                  background: t.role === 'user' ? '#3b82f6' : cardBg,
                  color: t.role === 'user' ? '#fff' : fg,
                }}>
                  {t.text}
                </div>
                {errors && errors.length > 0 && (
                  <div style={{ maxWidth: '85%', marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {errors.map((e, j) => (
                      <div key={j} style={{ fontSize: 11, display: 'flex', alignItems: 'baseline', gap: 4, flexWrap: 'wrap' }}>
                        <span style={{ color: '#ef4444', textDecoration: 'line-through' }}>{e.error}</span>
                        <span style={{ color: muted }}>→</span>
                        <span style={{ color: '#22c55e' }}>{e.correction}</span>
                        <span style={{ color: muted, fontSize: 10 }}>({e.brief})</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          <div ref={transcriptEndRef} />
        </div>

        {/* Controls */}
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${border}`, display: 'flex', justifyContent: 'center', gap: 16 }}>
          <button
            onClick={voice.toggleMic}
            style={{
              width: 48, height: 48, borderRadius: '50%', border: 'none', cursor: 'pointer',
              background: voice.isMicActive ? '#3b82f6' : '#ef4444',
              color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            title={voice.isMicActive ? 'Mute' : 'Unmute'}
          >
            {voice.isMicActive ? <Mic size={20} /> : <MicOff size={20} />}
          </button>
          <button
            onClick={() => { voice.stop(); handleSessionEnded() }}
            style={{
              width: 48, height: 48, borderRadius: '50%', border: 'none', cursor: 'pointer',
              background: '#ef4444', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            title="End Session"
          >
            <Square size={20} />
          </button>
        </div>

        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
      </div>
    )
  }

  // ── Analyzing Phase ──
  if (phase === 'analyzing') {
    return (
      <div style={{ height: '100%', background: bg, color: fg, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
        <Loader2 size={32} style={{ color: '#3b82f6' }} className="animate-spin" />
        <div style={{ fontSize: 16, fontWeight: 500 }}>Analyzing your session...</div>
        <div style={{ color: muted, fontSize: 13 }}>This usually takes 10-20 seconds</div>
      </div>
    )
  }

  // ── Results Phase ──
  if (!analysis) {
    return (
      <div style={{ height: '100%', background: bg, color: fg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Loader2 size={24} className="animate-spin" style={{ color: muted }} />
      </div>
    )
  }

  const prof = analysis.overall_proficiency
  const fluency = analysis.fluency_pace
  const vocab = analysis.vocabulary
  const grammar = analysis.grammar

  return (
    <div style={{ height: '100%', background: bg, color: fg, overflowY: 'auto', padding: 16 }}>
      {/* CEFR Level Header */}
      {prof && (
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{
            display: 'inline-block', padding: '8px 24px', borderRadius: 12,
            background: CEFR_COLORS[prof.level] ?? '#6b7280', color: '#fff',
            fontSize: 24, fontWeight: 700, letterSpacing: 2,
          }}>
            {prof.level}
          </div>
          <div style={{ color: muted, fontSize: 13, marginTop: 6 }}>{prof.level_description}</div>
        </div>
      )}

      {/* Summary */}
      {analysis.session_summary && (
        <div style={{ background: cardBg, borderRadius: 10, padding: 12, marginBottom: 12, fontSize: 13, color: muted, lineHeight: 1.6 }}>
          {analysis.session_summary}
        </div>
      )}

      {/* Collapsible sections */}
      {prof && (
        <Section title="Proficiency" id="proficiency" expanded={expandedSections} toggle={toggleSection} border={border} fg={fg} cardBg={cardBg}>
          {prof.strengths?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: muted, marginBottom: 4 }}>Strengths</div>
              {prof.strengths.map((s, i) => <div key={i} style={{ fontSize: 13, color: '#22c55e', marginBottom: 2 }}>+ {s}</div>)}
            </div>
          )}
          {prof.areas_to_improve?.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: muted, marginBottom: 4 }}>Areas to Improve</div>
              {prof.areas_to_improve.map((a, i) => <div key={i} style={{ fontSize: 13, color: '#f97316', marginBottom: 2 }}>- {a}</div>)}
            </div>
          )}
        </Section>
      )}

      {fluency && (
        <Section title={`Fluency & Pace — ${fluency.overall_score}/10`} id="fluency" expanded={expandedSections} toggle={toggleSection} border={border} fg={fg} cardBg={cardBg}>
          <ScoreBar score={fluency.overall_score} lightMode={lightMode} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10, fontSize: 12 }}>
            <div><span style={{ color: muted }}>Speed:</span> {fluency.speaking_speed}</div>
            <div><span style={{ color: muted }}>Flow:</span> {fluency.flow_rating}</div>
            <div><span style={{ color: muted }}>Pauses:</span> {fluency.pause_frequency}</div>
            <div><span style={{ color: muted }}>Fillers:</span> {fluency.filler_word_count}</div>
          </div>
          {fluency.filler_words_used?.length > 0 && (
            <div style={{ fontSize: 12, color: muted, marginTop: 6 }}>
              Filler words: {fluency.filler_words_used.join(', ')}
            </div>
          )}
        </Section>
      )}

      {vocab && (
        <Section title={`Vocabulary — ${vocab.overall_score}/10`} id="vocabulary" expanded={expandedSections} toggle={toggleSection} border={border} fg={fg} cardBg={cardBg}>
          <ScoreBar score={vocab.overall_score} lightMode={lightMode} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10, fontSize: 12 }}>
            <div><span style={{ color: muted }}>Variety:</span> {vocab.variety_score}/10</div>
            <div><span style={{ color: muted }}>Level:</span> {vocab.complexity_level}</div>
          </div>
          {vocab.notable_good_usage?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: muted, marginBottom: 2 }}>Good Usage</div>
              {vocab.notable_good_usage.map((w, i) => <span key={i} style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 6, background: lightMode ? '#dcfce7' : '#14532d', color: lightMode ? '#166534' : '#86efac', fontSize: 12, marginRight: 4, marginBottom: 4 }}>{w}</span>)}
            </div>
          )}
          {vocab.suggestions?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: muted, marginBottom: 2 }}>Suggestions</div>
              {vocab.suggestions.map((s, i) => <div key={i} style={{ fontSize: 12, color: '#f97316' }}>- {s}</div>)}
            </div>
          )}
        </Section>
      )}

      {grammar && (
        <Section title={`Grammar — ${grammar.overall_score}/10`} id="grammar" expanded={expandedSections} toggle={toggleSection} border={border} fg={fg} cardBg={cardBg}>
          <ScoreBar score={grammar.overall_score} lightMode={lightMode} />
          {grammar.common_errors?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, color: muted, marginBottom: 4 }}>Errors Found</div>
              {grammar.common_errors.map((e, i) => (
                <div key={i} style={{ padding: '6px 8px', borderRadius: 6, background: lightMode ? '#fef2f2' : '#451a1a', marginBottom: 4 }}>
                  <div style={{ fontSize: 12, color: '#ef4444', textDecoration: 'line-through' }}>{e.error}</div>
                  <div style={{ fontSize: 12, color: '#22c55e' }}>{e.correction}</div>
                  {e.explanation && <div style={{ fontSize: 11, color: muted, marginTop: 2 }}>{e.explanation}</div>}
                </div>
              ))}
            </div>
          )}
          {grammar.notes && <div style={{ fontSize: 12, color: muted, marginTop: 6 }}>{grammar.notes}</div>}
        </Section>
      )}

      {analysis.practice_suggestions && analysis.practice_suggestions.length > 0 && (
        <Section title="Practice Suggestions" id="suggestions" expanded={expandedSections} toggle={toggleSection} border={border} fg={fg} cardBg={cardBg}>
          {analysis.practice_suggestions.map((s, i) => (
            <div key={i} style={{ fontSize: 13, marginBottom: 6, lineHeight: 1.5 }}>{i + 1}. {s}</div>
          ))}
        </Section>
      )}

      {/* New Session */}
      <div style={{ textAlign: 'center', marginTop: 20, paddingBottom: 16 }}>
        <button
          onClick={handleNewSession}
          style={{
            padding: '10px 24px', borderRadius: 10, border: `1px solid ${border}`,
            background: cardBg, color: fg, cursor: 'pointer', fontSize: 14,
            display: 'inline-flex', alignItems: 'center', gap: 8,
          }}
        >
          <RotateCcw size={16} /> New Session
        </button>
      </div>
    </div>
  )
}

function Section({ title, id, expanded, toggle, border, fg, cardBg, children }: {
  title: string; id: string; expanded: Set<string>; toggle: (k: string) => void
  border: string; fg: string; cardBg: string; children: React.ReactNode
}) {
  const isOpen = expanded.has(id)
  return (
    <div style={{ border: `1px solid ${border}`, borderRadius: 10, marginBottom: 8, overflow: 'hidden' }}>
      <button
        onClick={() => toggle(id)}
        style={{ width: '100%', padding: '10px 12px', background: cardBg, color: fg, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13, fontWeight: 600 }}
      >
        {title}
        {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {isOpen && <div style={{ padding: 12 }}>{children}</div>}
    </div>
  )
}
