import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  Loader2, ArrowLeft, ArrowRight, Clock, CheckCircle2, AlertCircle, Download,
} from 'lucide-react'
import { Card, Button, Badge } from '../../components/ui'
import {
  employeeTrainingApi,
  type LessonResponse,
  type QuizResult,
  type AttestResult,
} from '../../api/hr/training'

type Stage = 'loading' | 'not_started' | 'in_progress' | 'quiz' | 'pass_attest' | 'completed' | 'failed'

const ATTESTATION_TEXT =
  "I attest that I personally completed all training modules and the assessment without assistance, and that the answers I submitted are my own."

function fmtCountdown(secs: number): string {
  if (secs <= 0) return '0:00'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function EmployeeTakeTraining() {
  const { recordId } = useParams<{ recordId: string }>()
  const navigate = useNavigate()
  const [stage, setStage] = useState<Stage>('loading')
  const [lesson, setLesson] = useState<LessonResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sectionIdx, setSectionIdx] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null)
  const [attesting, setAttesting] = useState(false)
  const [attested, setAttested] = useState<AttestResult | null>(null)
  const [attestChecked, setAttestChecked] = useState(false)

  // Server is the truth; client just shows a countdown.
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!recordId) return
    let alive = true
    void (async () => {
      try {
        const data = await employeeTrainingApi.lesson(recordId)
        if (!alive) return
        setLesson(data)
        if (data.status === 'completed') {
          setStage('completed')
        } else if (data.started_at) {
          setStage('in_progress')
        } else {
          setStage('not_started')
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load')
      }
    })()
    return () => {
      alive = false
    }
  }, [recordId])

  const requiredSeconds = lesson ? lesson.required_minutes * 60 : 0
  const elapsed = useMemo(() => {
    if (!lesson?.started_at) return 0
    return Math.floor((now - new Date(lesson.started_at).getTime()) / 1000)
  }, [lesson?.started_at, now])
  const remaining = Math.max(0, requiredSeconds - elapsed)
  const seatTimeMet = elapsed >= requiredSeconds

  async function startTraining() {
    if (!recordId) return
    try {
      const res = await employeeTrainingApi.start(recordId)
      setLesson((l) => (l ? { ...l, started_at: res.started_at, status: res.status } : l))
      setStage('in_progress')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start')
    }
  }

  async function submitQuiz() {
    if (!recordId) return
    try {
      const res = await employeeTrainingApi.submitQuiz(recordId, answers, elapsed)
      setQuizResult(res)
      setStage(res.passed ? 'pass_attest' : 'failed')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Quiz submission failed')
    }
  }

  async function attest() {
    if (!recordId || !attestChecked) return
    setAttesting(true)
    setError(null)
    try {
      const res = await employeeTrainingApi.attest(recordId, ATTESTATION_TEXT)
      setAttested(res)
      setStage('completed')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Attestation failed')
    } finally {
      setAttesting(false)
    }
  }

  async function downloadCert() {
    if (!recordId) return
    try {
      const { url } = await employeeTrainingApi.myCertificateUrl(recordId)
      window.open(url, '_blank', 'noopener')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to load certificate')
    }
  }

  if (error) {
    return (
      <div className="max-w-3xl">
        <Card className="p-6 bg-red-500/5 border-red-500/20">
          <div className="flex items-center gap-2 text-red-300">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        </Card>
      </div>
    )
  }

  if (!lesson || stage === 'loading') {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  return (
    <div className="max-w-3xl">
      <button
        onClick={() => navigate('/portal')}
        className="text-zinc-500 hover:text-zinc-300 text-sm flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-3 h-3" /> Back
      </button>

      <h1 className="text-2xl font-semibold text-zinc-100 mb-2">{lesson.title}</h1>
      <div className="flex items-center gap-3 mb-6">
        <Badge variant="neutral">
          {lesson.variant === 'supervisor' ? 'Supervisor' : 'Employee'}
        </Badge>
        <Badge variant="neutral">{lesson.required_minutes} min minimum</Badge>
        <Badge variant="neutral">Pass {lesson.pass_score_percent}%</Badge>
      </div>

      {stage === 'not_started' && (
        <Card className="p-6">
          <h2 className="text-base font-medium text-zinc-100 mb-2">Begin training</h2>
          <p className="text-sm text-zinc-400 mb-4">
            This module covers California SB 1343 harassment-prevention requirements.
            You must spend a minimum of <strong>{lesson.required_minutes} minutes</strong> on
            the lesson before the quiz unlocks. After passing the quiz, you'll attest to
            completion and receive a certificate.
          </p>
          <Button variant="primary" onClick={startTraining}>
            Begin training
          </Button>
        </Card>
      )}

      {stage === 'in_progress' && (
        <>
          <Card className="p-4 mb-4 flex items-center gap-3 bg-zinc-900/50">
            <Clock className="w-4 h-4 text-emerald-400" />
            <span className="text-sm text-zinc-300">
              {seatTimeMet ? (
                <strong className="text-emerald-300">Minimum seat time met</strong>
              ) : (
                <>
                  <strong>{fmtCountdown(remaining)}</strong> remaining before quiz unlocks
                </>
              )}
            </span>
          </Card>

          <Card className="p-6 mb-4">
            <div className="flex items-center justify-between text-xs text-zinc-500 mb-4">
              <span>
                Section {sectionIdx + 1} of {lesson.sections.length}
              </span>
              <span>{lesson.sections[sectionIdx]?.estimated_minutes ?? '—'} min</span>
            </div>
            <h2 className="text-lg font-semibold text-zinc-100 mb-4">
              {lesson.sections[sectionIdx]?.title}
            </h2>
            <article className="prose prose-invert prose-sm max-w-none text-zinc-200">
              <ReactMarkdown>{lesson.sections[sectionIdx]?.body_md ?? ''}</ReactMarkdown>
            </article>
            {lesson.sections[sectionIdx]?.key_takeaways &&
              lesson.sections[sectionIdx]!.key_takeaways!.length > 0 && (
                <div className="mt-6 p-4 bg-emerald-500/5 border-l-2 border-emerald-500/40 rounded">
                  <div className="text-xs uppercase tracking-wider text-emerald-400 mb-2">
                    Key takeaways
                  </div>
                  <ul className="text-sm text-zinc-200 space-y-1 list-disc pl-5">
                    {lesson.sections[sectionIdx]!.key_takeaways!.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}
          </Card>

          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              disabled={sectionIdx === 0}
              onClick={() => setSectionIdx((i) => Math.max(0, i - 1))}
            >
              <ArrowLeft className="w-3 h-3 mr-1" /> Previous
            </Button>
            {sectionIdx < lesson.sections.length - 1 ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setSectionIdx((i) => i + 1)}
              >
                Next <ArrowRight className="w-3 h-3 ml-1" />
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                disabled={!seatTimeMet}
                onClick={() => setStage('quiz')}
              >
                {seatTimeMet ? 'Take quiz' : `Quiz unlocks in ${fmtCountdown(remaining)}`}
              </Button>
            )}
          </div>
        </>
      )}

      {stage === 'quiz' && (
        <Card className="p-6">
          <h2 className="text-base font-semibold text-zinc-100 mb-4">Quiz</h2>
          <div className="space-y-6">
            {lesson.quiz.questions.map((q, i) => (
              <div key={q.id}>
                <div className="text-sm font-medium text-zinc-100 mb-3">
                  {i + 1}. {q.prompt}
                </div>
                <div className="space-y-2">
                  {q.options.map((o) => (
                    <label
                      key={o.key}
                      className={`flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
                        answers[q.id] === o.key
                          ? 'bg-emerald-500/10 border-emerald-500/50'
                          : 'bg-zinc-900 border-zinc-800 hover:border-zinc-700'
                      }`}
                    >
                      <input
                        type="radio"
                        name={q.id}
                        value={o.key}
                        checked={answers[q.id] === o.key}
                        onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.key }))}
                        className="mt-0.5"
                      />
                      <span className="text-sm text-zinc-200">
                        <span className="text-zinc-500 mr-2">{o.key}.</span>
                        {o.text}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-6 flex items-center justify-end gap-3">
            <Button variant="ghost" size="sm" onClick={() => setStage('in_progress')}>
              Back to lesson
            </Button>
            <Button
              variant="primary"
              disabled={Object.keys(answers).length < lesson.quiz.questions.length}
              onClick={submitQuiz}
            >
              Submit answers
            </Button>
          </div>
        </Card>
      )}

      {stage === 'pass_attest' && quizResult && (
        <Card className="p-6">
          <div className="flex items-center gap-2 text-emerald-400 mb-2">
            <CheckCircle2 className="w-5 h-5" />
            <span className="text-base font-semibold">Passed</span>
          </div>
          <p className="text-sm text-zinc-300 mb-1">
            Score: <strong>{quizResult.score_percent.toFixed(1)}%</strong> ({quizResult.correct} of{' '}
            {quizResult.total} correct)
          </p>
          <p className="text-xs text-zinc-500 mb-6">Pass threshold: {quizResult.pass_score_percent}%</p>

          <div className="border-t border-zinc-800 pt-5 mt-2">
            <h3 className="text-sm font-semibold text-zinc-100 mb-2">Attestation</h3>
            <p className="text-sm text-zinc-300 leading-relaxed mb-4 whitespace-pre-wrap">
              {ATTESTATION_TEXT}
            </p>
            <label className="flex items-center gap-2 mb-4 text-sm text-zinc-200 cursor-pointer">
              <input
                type="checkbox"
                checked={attestChecked}
                onChange={(e) => setAttestChecked(e.target.checked)}
              />
              I attest to the statement above.
            </label>
            <Button
              variant="primary"
              disabled={!attestChecked || attesting}
              onClick={attest}
            >
              {attesting ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Generating certificate…
                </span>
              ) : (
                'Confirm and generate certificate'
              )}
            </Button>
          </div>
        </Card>
      )}

      {stage === 'failed' && quizResult && (
        <Card className="p-6 bg-amber-500/5 border-amber-500/20">
          <div className="flex items-center gap-2 text-amber-300 mb-2">
            <AlertCircle className="w-5 h-5" />
            <span className="text-base font-semibold">Did not pass</span>
          </div>
          <p className="text-sm text-zinc-300 mb-1">
            Score: <strong>{quizResult.score_percent.toFixed(1)}%</strong> (need{' '}
            {quizResult.pass_score_percent}%)
          </p>
          <p className="text-xs text-zinc-500 mb-6">
            You can retake the quiz. Each attempt is recorded for compliance.
          </p>
          <Button
            variant="primary"
            onClick={() => {
              setAnswers({})
              setQuizResult(null)
              setStage('quiz')
            }}
          >
            Retake quiz
          </Button>
        </Card>
      )}

      {stage === 'completed' && (
        <Card className="p-8 text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10 mb-4">
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
          </div>
          <h2 className="text-lg font-semibold text-zinc-100 mb-2">Training complete</h2>
          {attested && (
            <p className="text-sm text-zinc-400 mb-1">
              Score {attested.score_percent.toFixed(1)}% · Valid until{' '}
              {attested.expiration_date}
            </p>
          )}
          <p className="text-xs text-zinc-500 mb-6">
            Your certificate has been emailed to you and stored on file.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="primary" onClick={downloadCert}>
              <Download className="w-4 h-4 mr-1" /> Download certificate
            </Button>
            <Button variant="ghost" onClick={() => navigate('/portal')}>
              Back to dashboard
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
