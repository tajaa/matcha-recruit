import { useState, useEffect, useRef, useCallback } from 'react'
import { useVoiceSession } from '../../hooks/useVoiceSession'
import { startTutorSession, getTutorStatus, checkUtterance, type TutorStartResponse, type TutorAnalysis, type UtteranceError } from '../../api/matchaWork'

export type PanelPhase = 'setup' | 'active' | 'analyzing' | 'results'

export interface Transcript {
  role: 'user' | 'assistant'
  text: string
}

interface UseLanguageTutorPanelArgs {
  threadId: string
  lightMode: boolean
  currentState: Record<string, unknown> | null
  onStateUpdate?: () => void
}

export function useLanguageTutorPanel({ threadId, lightMode, currentState, onStateUpdate }: UseLanguageTutorPanelArgs) {
  // Recover state from current_state if session already exists
  const tutorState = (currentState?.language_tutor as { interview_id?: string; language?: string; status?: string; message_saved?: boolean }) ?? null

  const [phase, setPhase] = useState<PanelPhase>(() => {
    if (!tutorState) return 'setup'
    if (tutorState.status === 'completed' || tutorState.message_saved) return 'results'
    if (tutorState.status === 'active') return 'setup' // WS disconnected, let user restart
    return 'setup'
  })
  const [language, setLanguage] = useState<'en' | 'es-mx' | 'fr'>(
    (tutorState?.language as 'en' | 'es-mx' | 'fr') ?? 'en'
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

  return {
    // colors
    bg,
    fg,
    muted,
    cardBg,
    border,
    // state
    phase,
    language,
    setLanguage,
    duration,
    setDuration,
    transcripts,
    sessionInfo,
    analysis,
    error,
    starting,
    expandedSections,
    inlineErrors,
    // refs
    transcriptEndRef,
    // voice
    voice,
    // handlers
    handleStart,
    handleNewSession,
    toggleSection,
    handleSessionEnded,
  }
}
