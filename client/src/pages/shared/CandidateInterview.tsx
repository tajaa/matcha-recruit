import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Video, CheckCircle2, XCircle, AlertTriangle, Mic, MicOff, Square } from 'lucide-react'
import { Logo } from '../../components/ui'
import { useVoiceSession } from '../../hooks/useVoiceSession'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type PageState = 'loading' | 'ready' | 'in_progress' | 'starting' | 'active' | 'completed' | 'not_found' | 'expired' | 'error'

interface InviteInfo {
  candidate_name: string
  position_title: string
  company_name: string
  status: string
}

interface SessionInfo {
  interview_id: string
  websocket_url: string
  ws_auth_token: string
  max_session_duration_seconds: number
}

interface Transcript {
  role: 'user' | 'assistant'
  text: string
}

function formatTime(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function CandidateInterview() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<PageState>('loading')
  const [info, setInfo] = useState<InviteInfo | null>(null)
  const [error, setError] = useState('')
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null)
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const transcriptEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!token) { setState('not_found'); return }
    fetch(`${BASE}/candidate-interview/${token}`)
      .then(async (res) => {
        if (res.status === 404) { setState('not_found'); return }
        if (res.status === 410) { setState('expired'); return }
        if (!res.ok) { setState('error'); setError(`Unexpected error (${res.status})`); return }
        const data = await res.json()
        setInfo(data)
        if (data.status === 'completed' || data.status === 'analyzed') setState('completed')
        else if (data.status === 'in_progress') setState('in_progress')
        else setState('ready')
      })
      .catch(() => { setState('error'); setError('Network error. Please check your connection.') })
  }, [token])

  // Auto-scroll transcripts
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts.length])

  const handleTranscript = useCallback((role: 'user' | 'assistant', text: string) => {
    if (!text.trim()) return
    setTranscripts((prev) => [...prev, { role, text }])
  }, [])

  const handleSessionEnded = useCallback(() => {
    setState('completed')
    setSessionInfo(null)
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

  // If voice errors out, show error state
  useEffect(() => {
    if (voiceStatus === 'error' && state === 'active') {
      setError('Could not connect to voice interview. Please check your microphone permissions and try again.')
      setState('error')
    }
  }, [voiceStatus, state])

  async function handleStart() {
    if (!token) return
    setState('starting')
    setTranscripts([])
    try {
      const res = await fetch(`${BASE}/candidate-interview/${token}/start`, { method: 'POST' })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setError(body?.detail || `Failed to start (${res.status})`)
        setState('error')
        return
      }
      const data = await res.json()
      if (data.status === 'completed') { setState('completed'); return }
      setSessionInfo({
        interview_id: data.interview_id,
        websocket_url: data.websocket_url,
        ws_auth_token: data.ws_auth_token,
        max_session_duration_seconds: data.max_session_duration_seconds,
      })
      setState('active')
    } catch {
      setError('Network error. Please try again.')
      setState('error')
    }
  }

  const maxSec = sessionInfo?.max_session_duration_seconds ?? 30

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Logo className="justify-center mb-8 grayscale" />

        <div className="border border-zinc-800 rounded-xl p-6">
          {state === 'loading' && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
              <p className="text-sm text-zinc-500">Loading interview details...</p>
            </div>
          )}

          {(state === 'ready' || state === 'in_progress') && info && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <Video size={18} className="text-emerald-400" />
                <h1 className="text-lg font-semibold text-zinc-100">
                  Screening Interview
                </h1>
              </div>
              <div className="space-y-2 mb-5">
                <p className="text-sm text-zinc-300">
                  Hi <span className="font-medium text-zinc-100">{info.candidate_name}</span>,
                </p>
                <p className="text-sm text-zinc-400">
                  You've been invited to a screening interview for{' '}
                  <span className="text-zinc-200 font-medium">{info.position_title}</span> at{' '}
                  <span className="text-zinc-200 font-medium">{info.company_name}</span>.
                </p>
                <p className="text-sm text-zinc-500">
                  This is an AI-powered voice interview that takes about 10-15 minutes. No account or download required.
                </p>
                <p className="text-xs text-zinc-600 mt-2">
                  <Mic size={10} className="inline mr-1" />
                  Microphone access is required. You'll be prompted to allow it when you begin.
                </p>
              </div>
              <button
                onClick={handleStart}
                className="w-full py-2.5 text-sm font-medium rounded-lg transition-colors bg-emerald-600 hover:bg-emerald-500 text-white"
              >
                {state === 'in_progress' ? 'Rejoin Interview' : 'Begin Interview'}
              </button>
            </>
          )}

          {state === 'starting' && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 size={24} className="animate-spin text-emerald-400" />
              <p className="text-sm text-zinc-400">Starting your interview...</p>
            </div>
          )}

          {state === 'active' && info && (
            <div className="flex flex-col" style={{ minHeight: 360 }}>
              {/* Header with status + timer */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: voice.status === 'active' ? '#22c55e' : '#eab308',
                      animation: voice.status === 'active' ? 'pulse 2s infinite' : undefined,
                    }}
                  />
                  <span className="text-xs font-medium text-zinc-300">
                    {voice.status === 'connecting' ? 'Connecting...' : voice.status === 'active' ? 'Interview Active' : 'Finishing up...'}
                  </span>
                </div>
                <span className="text-xs font-mono text-zinc-500">
                  {formatTime(voice.elapsedSeconds)} / {formatTime(maxSec)}
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-1 rounded-full bg-zinc-800 mb-4 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-1000"
                  style={{
                    width: `${Math.min(100, (voice.elapsedSeconds / maxSec) * 100)}%`,
                    background: voice.elapsedSeconds >= maxSec * 0.8 ? '#f59e0b' : '#22c55e',
                  }}
                />
              </div>

              {/* Transcript area */}
              <div className="flex-1 overflow-y-auto space-y-3 mb-4" style={{ maxHeight: 220 }}>
                {transcripts.length === 0 && (
                  <div className="text-center py-8">
                    <p className="text-xs text-zinc-500">
                      {voice.status === 'connecting' ? 'Connecting to interviewer...' : 'Listening... The interviewer will begin shortly.'}
                    </p>
                  </div>
                )}
                {transcripts.map((t, i) => (
                  <div key={i} className={`flex flex-col ${t.role === 'user' ? 'items-end' : 'items-start'}`}>
                    <span className="text-[10px] text-zinc-600 mb-0.5">
                      {t.role === 'user' ? 'You' : 'Interviewer'}
                    </span>
                    <div
                      className="px-3 py-2 rounded-xl text-sm max-w-[85%]"
                      style={{
                        background: t.role === 'user' ? '#3b82f6' : '#27272a',
                        color: t.role === 'user' ? '#fff' : '#d4d4d8',
                      }}
                    >
                      {t.text}
                    </div>
                  </div>
                ))}
                <div ref={transcriptEndRef} />
              </div>

              {/* Controls */}
              <div className="flex items-center justify-center gap-4 pt-3" style={{ borderTop: '1px solid #27272a' }}>
                <button
                  onClick={voice.toggleMic}
                  className="w-10 h-10 rounded-full flex items-center justify-center transition-colors"
                  style={{
                    background: voice.isMicActive ? '#27272a' : '#ef4444',
                    color: voice.isMicActive ? '#d4d4d8' : '#fff',
                  }}
                  title={voice.isMicActive ? 'Mute microphone' : 'Unmute microphone'}
                >
                  {voice.isMicActive ? <Mic size={18} /> : <MicOff size={18} />}
                </button>
                <button
                  onClick={voice.stop}
                  className="w-10 h-10 rounded-full flex items-center justify-center bg-red-600 hover:bg-red-500 text-white transition-colors"
                  title="End interview"
                >
                  <Square size={16} />
                </button>
              </div>
            </div>
          )}

          {state === 'completed' && (
            <div className="text-center py-4">
              <CheckCircle2 size={32} className="text-emerald-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Interview Complete</h2>
              <p className="text-sm text-zinc-400">
                Thank you for completing your interview. The hiring team will review your responses and follow up.
              </p>
            </div>
          )}

          {state === 'not_found' && (
            <div className="text-center py-4">
              <XCircle size={32} className="text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Invalid Link</h2>
              <p className="text-sm text-zinc-400">
                This interview link is invalid or has expired. Please contact the hiring team for a new link.
              </p>
            </div>
          )}

          {state === 'expired' && (
            <div className="text-center py-4">
              <AlertTriangle size={32} className="text-amber-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Interview Cancelled</h2>
              <p className="text-sm text-zinc-400">
                This interview has been cancelled. Please contact the hiring team if you believe this is an error.
              </p>
            </div>
          )}

          {state === 'error' && (
            <div className="text-center py-4">
              <XCircle size={32} className="text-red-400 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-zinc-100 mb-2">Something Went Wrong</h2>
              <p className="text-sm text-red-400 mb-4">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="text-sm text-zinc-400 underline hover:text-zinc-200"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
