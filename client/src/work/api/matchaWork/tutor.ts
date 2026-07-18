import { api } from '../../../api/client'

// ── Language Tutor Voice ──────────────────────────────────────────

export interface TutorStartResponse {
  interview_id: string
  websocket_url: string
  ws_auth_token: string
  max_session_duration_seconds: number
}

export interface TutorAnalysis {
  fluency_pace?: {
    overall_score: number
    speaking_speed: string
    pause_frequency: string
    filler_word_count: number
    filler_words_used: string[]
    flow_rating: string
    notes: string
  }
  vocabulary?: {
    overall_score: number
    variety_score: number
    appropriateness_score: number
    complexity_level: string
    notable_good_usage: string[]
    suggestions: string[]
  }
  grammar?: {
    overall_score: number
    sentence_structure_score: number
    tense_usage_score: number
    common_errors: Array<{ error: string; correction: string; explanation?: string }>
    notes: string
  }
  overall_proficiency?: {
    level: string
    level_description: string
    strengths: string[]
    areas_to_improve: string[]
  }
  practice_suggestions?: string[]
  session_summary?: string
  language?: string
}

export interface TutorStatusResponse {
  status: string
  tutor_analysis: TutorAnalysis | null
}

export function startTutorSession(threadId: string, language: 'en' | 'es-mx' | 'fr', durationMinutes = 5) {
  return api.post<TutorStartResponse>(`/matcha-work/threads/${threadId}/tutor/start`, {
    language,
    duration_minutes: durationMinutes,
  })
}

export function getTutorStatus(threadId: string) {
  return api.get<TutorStatusResponse>(`/matcha-work/threads/${threadId}/tutor/status`)
}

export interface UtteranceError {
  error: string
  correction: string
  type: 'grammar' | 'vocabulary' | 'pronunciation'
  brief: string
}

export function checkUtterance(threadId: string, utterance: string, language: 'en' | 'es-mx' | 'fr') {
  return api.post<{ errors: UtteranceError[] }>(`/matcha-work/threads/${threadId}/tutor/check`, {
    utterance,
    language,
  })
}
