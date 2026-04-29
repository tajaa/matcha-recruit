import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ChevronRight, Mail } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'
import {
  AuditAnswer,
  Finding,
  INDUSTRIES,
  QUESTIONS,
  computeFindings,
  computeScore,
} from './auditRules'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Step = 'intro' | 'context' | 'questions' | 'results'

const STATES_50: { slug: string; name: string }[] = [
  ['alabama', 'Alabama'], ['alaska', 'Alaska'], ['arizona', 'Arizona'], ['arkansas', 'Arkansas'],
  ['california', 'California'], ['colorado', 'Colorado'], ['connecticut', 'Connecticut'],
  ['delaware', 'Delaware'], ['district-of-columbia', 'District of Columbia'], ['florida', 'Florida'],
  ['georgia', 'Georgia'], ['hawaii', 'Hawaii'], ['idaho', 'Idaho'], ['illinois', 'Illinois'],
  ['indiana', 'Indiana'], ['iowa', 'Iowa'], ['kansas', 'Kansas'], ['kentucky', 'Kentucky'],
  ['louisiana', 'Louisiana'], ['maine', 'Maine'], ['maryland', 'Maryland'], ['massachusetts', 'Massachusetts'],
  ['michigan', 'Michigan'], ['minnesota', 'Minnesota'], ['mississippi', 'Mississippi'],
  ['missouri', 'Missouri'], ['montana', 'Montana'], ['nebraska', 'Nebraska'], ['nevada', 'Nevada'],
  ['new-hampshire', 'New Hampshire'], ['new-jersey', 'New Jersey'], ['new-mexico', 'New Mexico'],
  ['new-york', 'New York'], ['north-carolina', 'North Carolina'], ['north-dakota', 'North Dakota'],
  ['ohio', 'Ohio'], ['oklahoma', 'Oklahoma'], ['oregon', 'Oregon'], ['pennsylvania', 'Pennsylvania'],
  ['rhode-island', 'Rhode Island'], ['south-carolina', 'South Carolina'], ['south-dakota', 'South Dakota'],
  ['tennessee', 'Tennessee'], ['texas', 'Texas'], ['utah', 'Utah'], ['vermont', 'Vermont'],
  ['virginia', 'Virginia'], ['washington', 'Washington'], ['west-virginia', 'West Virginia'],
  ['wisconsin', 'Wisconsin'], ['wyoming', 'Wyoming'],
].map(([slug, name]) => ({ slug, name }))

const SEVERITY_BG: Record<Finding['severity'], string> = {
  high: 'rgba(193, 84, 58, 0.08)',
  medium: 'rgba(193, 159, 58, 0.08)',
  low: 'rgba(90, 140, 90, 0.08)',
}
const SEVERITY_COLOR: Record<Finding['severity'], string> = {
  high: '#c1543a',
  medium: '#c19f3a',
  low: '#5a8c5a',
}

export default function ComplianceAudit() {
  const [step, setStep] = useState<Step>('intro')
  const [stateSlug, setStateSlug] = useState('')
  const [headcount, setHeadcount] = useState<number | ''>('')
  const [industry, setIndustry] = useState<string>(INDUSTRIES[0])
  const [answers, setAnswers] = useState<Record<string, AuditAnswer>>({})
  const [questionIdx, setQuestionIdx] = useState(0)
  const [showPricing, setShowPricing] = useState(false)

  // Email step (post-results)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [emailing, setEmailing] = useState(false)
  const [emailDone, setEmailDone] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  useEffect(() => {
    document.title = 'HR Compliance Audit — Matcha'
  }, [])

  const findings = useMemo(() => (step === 'results' ? computeFindings(answers) : []), [step, answers])
  const score = useMemo(() => (step === 'results' ? computeScore(answers) : null), [step, answers])
  const allAnswered = QUESTIONS.every(q => answers[q.id])

  const setAnswer = (id: string, a: AuditAnswer) => {
    setAnswers(prev => ({ ...prev, [id]: a }))
    if (questionIdx < QUESTIONS.length - 1) {
      setTimeout(() => setQuestionIdx(i => Math.min(i + 1, QUESTIONS.length - 1)), 150)
    }
  }

  const submitEmail = async () => {
    if (!email.includes('@')) {
      setEmailError('Enter a valid email.')
      return
    }
    setEmailing(true)
    setEmailError(null)
    try {
      await api.post('/resources/audit', {
        email: email.trim(),
        name: name.trim() || undefined,
        state_slug: stateSlug || undefined,
        headcount: typeof headcount === 'number' ? headcount : undefined,
        industry,
        findings,
        score: score?.score,
        answered: score?.answered,
        total: score?.total,
      })
      setEmailDone(true)
    } catch (err: any) {
      setEmailError(err?.message ?? 'Failed to send.')
    } finally {
      setEmailing(false)
    }
  }

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[820px] mx-auto px-6 sm:px-10">
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to="/resources" className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>Compliance Audit</span>
        </nav>

        {step === 'intro' && <Intro onStart={() => setStep('context')} />}

        {step === 'context' && (
          <Context
            stateSlug={stateSlug}
            setStateSlug={setStateSlug}
            headcount={headcount}
            setHeadcount={setHeadcount}
            industry={industry}
            setIndustry={setIndustry}
            onBack={() => setStep('intro')}
            onNext={() => setStep('questions')}
          />
        )}

        {step === 'questions' && (
          <Questions
            idx={questionIdx}
            setIdx={setQuestionIdx}
            answers={answers}
            setAnswer={setAnswer}
            onFinish={() => setStep('results')}
            allAnswered={allAnswered}
          />
        )}

        {step === 'results' && score && (
          <Results
            score={score.score}
            findings={findings}
            stateSlug={stateSlug}
            email={email}
            setEmail={setEmail}
            name={name}
            setName={setName}
            emailing={emailing}
            emailError={emailError}
            emailDone={emailDone}
            onEmail={submitEmail}
            onRestart={() => {
              setStep('intro')
              setAnswers({})
              setQuestionIdx(0)
              setEmail('')
              setName('')
              setEmailDone(false)
              setEmailError(null)
            }}
            onSeePricing={() => setShowPricing(true)}
          />
        )}
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}

function Intro({ onStart }: { onStart: () => void }) {
  return (
    <>
      <header className="mb-10">
        <h1
          className="text-5xl sm:text-6xl tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
        >
          12-Question HR Compliance Audit
        </h1>
        <p className="mt-4 text-base" style={{ color: MUTED }}>
          A 3-minute self-audit covering the highest-cost compliance
          areas: posters, handbooks, I-9s, classification, leave,
          harassment, records, terminations, background checks, pay
          transparency, and lactation accommodation.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-10">
        {[
          { n: '12', l: 'questions' },
          { n: '~3', l: 'minutes' },
          { n: 'PDF', l: 'gap report emailed' },
        ].map(s => (
          <div
            key={s.l}
            className="p-5 rounded-xl text-center"
            style={{ border: `1px solid ${LINE}` }}
          >
            <div className="text-3xl mb-1" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>{s.n}</div>
            <div className="text-xs" style={{ color: MUTED }}>{s.l}</div>
          </div>
        ))}
      </div>

      <button
        onClick={onStart}
        className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 h-12 rounded-full text-sm font-medium"
        style={{ backgroundColor: INK, color: BG }}
      >
        Start the audit <ArrowRight className="w-4 h-4" />
      </button>

      <p className="text-xs mt-6" style={{ color: MUTED }}>
        No login required. We don't collect your responses unless you
        choose to email yourself the gap report. Informational only —
        not legal advice.
      </p>
    </>
  )
}

function Context(props: {
  stateSlug: string; setStateSlug: (s: string) => void
  headcount: number | ''; setHeadcount: (n: number | '') => void
  industry: string; setIndustry: (s: string) => void
  onBack: () => void; onNext: () => void
}) {
  return (
    <>
      <header className="mb-8">
        <p className="text-xs uppercase tracking-wider mb-2" style={{ color: MUTED }}>Step 1 of 2</p>
        <h2 className="text-3xl" style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}>
          Tell us about your business
        </h2>
        <p className="mt-2 text-sm" style={{ color: MUTED }}>
          Used to tailor your gap report. Not stored unless you email yourself the results.
        </p>
      </header>

      <div className="flex flex-col gap-5 mb-10">
        <div>
          <label className="block text-xs mb-2" style={{ color: MUTED }}>Primary state</label>
          <select
            value={props.stateSlug}
            onChange={e => props.setStateSlug(e.target.value)}
            className="w-full px-4 h-11 rounded-lg text-sm outline-none"
            style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
          >
            <option value="">— Select state —</option>
            {STATES_50.map(s => (
              <option key={s.slug} value={s.slug}>{s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs mb-2" style={{ color: MUTED }}>Headcount (US employees)</label>
          <input
            type="number"
            min={1}
            value={props.headcount}
            onChange={e => props.setHeadcount(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-4 h-11 rounded-lg text-sm outline-none"
            style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
          />
        </div>
        <div>
          <label className="block text-xs mb-2" style={{ color: MUTED }}>Industry</label>
          <select
            value={props.industry}
            onChange={e => props.setIndustry(e.target.value)}
            className="w-full px-4 h-11 rounded-lg text-sm outline-none"
            style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
          >
            {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={props.onBack}
          className="inline-flex items-center gap-2 text-sm transition-opacity hover:opacity-60"
          style={{ color: INK }}
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <button
          onClick={props.onNext}
          className="inline-flex items-center gap-2 px-6 h-11 rounded-full text-sm font-medium"
          style={{ backgroundColor: INK, color: BG }}
        >
          Continue <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </>
  )
}

function Questions(props: {
  idx: number; setIdx: (n: number) => void
  answers: Record<string, AuditAnswer>
  setAnswer: (id: string, a: AuditAnswer) => void
  onFinish: () => void
  allAnswered: boolean
}) {
  const q = QUESTIONS[props.idx]
  const progress = ((props.idx + 1) / QUESTIONS.length) * 100

  return (
    <>
      <div className="mb-8">
        <p className="text-xs uppercase tracking-wider mb-2" style={{ color: MUTED }}>
          Step 2 of 2 &middot; Question {props.idx + 1} of {QUESTIONS.length}
        </p>
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ backgroundColor: 'rgba(15,15,15,0.08)' }}
        >
          <div
            className="h-full transition-all"
            style={{ width: `${progress}%`, backgroundColor: INK }}
          />
        </div>
      </div>

      <article
        className="p-8 rounded-2xl mb-8"
        style={{ border: `1px solid ${LINE}` }}
      >
        <p className="text-xs uppercase tracking-wider mb-3" style={{ color: MUTED }}>
          {q.category}
        </p>
        <h2
          className="text-2xl mb-4"
          style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK, lineHeight: 1.3 }}
        >
          {q.question}
        </h2>
        {q.helper && (
          <p className="text-sm mb-6" style={{ color: MUTED }}>{q.helper}</p>
        )}

        <div className="grid grid-cols-3 gap-3">
          {(['yes', 'no', 'unsure'] as AuditAnswer[]).map(a => {
            const selected = props.answers[q.id] === a
            return (
              <button
                key={a}
                onClick={() => props.setAnswer(q.id, a)}
                className="h-12 rounded-lg text-sm font-medium capitalize transition-colors"
                style={{
                  backgroundColor: selected ? INK : 'transparent',
                  color: selected ? BG : INK,
                  border: `1px solid ${selected ? INK : LINE}`,
                }}
              >
                {a}
              </button>
            )
          })}
        </div>
      </article>

      <div className="flex items-center justify-between">
        <button
          onClick={() => props.setIdx(Math.max(0, props.idx - 1))}
          disabled={props.idx === 0}
          className="inline-flex items-center gap-2 text-sm transition-opacity hover:opacity-60 disabled:opacity-30"
          style={{ color: INK }}
        >
          <ArrowLeft className="w-4 h-4" /> Previous
        </button>

        {props.idx === QUESTIONS.length - 1 ? (
          <button
            onClick={props.onFinish}
            disabled={!props.allAnswered}
            className="inline-flex items-center gap-2 px-6 h-11 rounded-full text-sm font-medium disabled:opacity-50"
            style={{ backgroundColor: INK, color: BG }}
          >
            See my report <ArrowRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => props.setIdx(Math.min(QUESTIONS.length - 1, props.idx + 1))}
            className="inline-flex items-center gap-2 text-sm transition-opacity hover:opacity-60"
            style={{ color: INK }}
          >
            Next <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </>
  )
}

function Results(props: {
  score: number
  findings: Finding[]
  stateSlug: string
  email: string; setEmail: (s: string) => void
  name: string; setName: (s: string) => void
  emailing: boolean; emailError: string | null; emailDone: boolean
  onEmail: () => void
  onRestart: () => void
  onSeePricing: () => void
}) {
  const grade =
    props.score >= 90 ? 'A — Strong'
    : props.score >= 75 ? 'B — Solid, gaps to close'
    : props.score >= 60 ? 'C — Material gaps'
    : props.score >= 40 ? 'D — High risk'
    : 'F — Urgent attention needed'
  const gradeColor =
    props.score >= 75 ? '#5a8c5a'
    : props.score >= 60 ? '#c19f3a'
    : '#c1543a'

  const high = props.findings.filter(f => f.severity === 'high')
  const med = props.findings.filter(f => f.severity === 'medium')
  const low = props.findings.filter(f => f.severity === 'low')

  return (
    <>
      <header className="mb-10">
        <p className="text-xs uppercase tracking-wider mb-2" style={{ color: MUTED }}>Your Gap Report</p>
        <h2
          className="text-4xl sm:text-5xl tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
        >
          Compliance score: {props.score}/100
        </h2>
        <p className="mt-3 text-lg" style={{ color: gradeColor, fontFamily: DISPLAY }}>
          {grade}
        </p>
      </header>

      <div className="grid grid-cols-3 gap-3 mb-10">
        <ScoreBox label="High severity" n={high.length} color="#c1543a" />
        <ScoreBox label="Medium" n={med.length} color="#c19f3a" />
        <ScoreBox label="Low / clear" n={low.length || (QUESTIONS.length - props.findings.length)} color="#5a8c5a" />
      </div>

      {props.findings.length > 0 ? (
        <section className="mb-12">
          <h3
            className="text-2xl mb-6"
            style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
          >
            Flagged Gaps ({props.findings.length})
          </h3>
          <div className="flex flex-col gap-3">
            {props.findings.map(f => (
              <article
                key={f.id}
                className="p-5 rounded-xl"
                style={{
                  border: `1px solid ${LINE}`,
                  backgroundColor: SEVERITY_BG[f.severity],
                  borderLeft: `3px solid ${SEVERITY_COLOR[f.severity]}`,
                }}
              >
                <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
                  <h4 className="text-base" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
                    {f.title}
                  </h4>
                  <span
                    className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded"
                    style={{ color: SEVERITY_COLOR[f.severity], border: `1px solid ${SEVERITY_COLOR[f.severity]}` }}
                  >
                    {f.severity}
                  </span>
                </div>
                <p className="text-xs uppercase tracking-wider mb-2" style={{ color: MUTED }}>
                  {f.category}
                </p>
                <p className="text-sm" style={{ color: INK, opacity: 0.85, lineHeight: 1.6 }}>
                  {f.detail}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : (
        <section
          className="mb-12 p-8 rounded-xl text-center"
          style={{ border: `1px solid ${LINE}`, backgroundColor: SEVERITY_BG.low }}
        >
          <h3 className="text-xl" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            No gaps flagged.
          </h3>
          <p className="mt-2 text-sm" style={{ color: MUTED }}>
            Strong compliance posture. Re-run quarterly as laws change.
          </p>
        </section>
      )}

      <section
        className="p-6 rounded-2xl mb-8"
        style={{ border: `1px solid ${LINE}` }}
      >
        <h3 className="text-xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
          Email yourself a copy
        </h3>
        <p className="text-sm mb-5" style={{ color: MUTED }}>
          We'll send the full gap report so you can share with your team
          or revisit later.
        </p>
        {props.emailDone ? (
          <p className="text-sm" style={{ color: '#5a8c5a' }}>
            Sent to {props.email}. Check your inbox.
          </p>
        ) : (
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              placeholder="you@company.com"
              value={props.email}
              onChange={e => props.setEmail(e.target.value)}
              className="flex-1 px-4 h-11 rounded-lg text-sm outline-none"
              style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
            />
            <input
              type="text"
              placeholder="Name (optional)"
              value={props.name}
              onChange={e => props.setName(e.target.value)}
              className="px-4 h-11 rounded-lg text-sm outline-none w-full sm:w-44"
              style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
            />
            <button
              onClick={props.onEmail}
              disabled={props.emailing}
              className="inline-flex items-center justify-center gap-2 px-5 h-11 rounded-full text-sm font-medium disabled:opacity-50"
              style={{ backgroundColor: INK, color: BG }}
            >
              <Mail className="w-4 h-4" />
              {props.emailing ? 'Sending…' : 'Email me'}
            </button>
          </div>
        )}
        {props.emailError && (
          <p className="text-sm mt-2" style={{ color: '#c1543a' }}>{props.emailError}</p>
        )}
      </section>

      <section
        className="p-8 rounded-2xl mb-8"
        style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
      >
        <h3 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
          Close these gaps with Matcha
        </h3>
        <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
          Matcha generates the missing policies, tracks every state and
          local rule, and re-runs your audit automatically as laws change
          — so the score above doesn't quietly slip.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={props.onSeePricing}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ backgroundColor: INK, color: BG }}
          >
            See Matcha →
          </button>
          {props.stateSlug && (
            <Link
              to={`/resources/states/${props.stateSlug}`}
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ border: `1px solid ${LINE}`, color: INK }}
            >
              View {props.stateSlug.replace(/-/g, ' ')} requirements
            </Link>
          )}
          <button
            onClick={props.onRestart}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ border: `1px solid ${LINE}`, color: INK }}
          >
            Restart audit
          </button>
        </div>
      </section>

      <p className="text-xs" style={{ color: MUTED }}>
        This audit is informational only and not legal advice. Consult
        employment counsel for your specific situation.
      </p>
    </>
  )
}

function ScoreBox({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <div
      className="p-5 rounded-xl text-center"
      style={{ border: `1px solid ${LINE}` }}
    >
      <div
        className="text-4xl mb-1"
        style={{ fontFamily: DISPLAY, fontWeight: 500, color }}
      >
        {n}
      </div>
      <div className="text-xs" style={{ color: MUTED }}>{label}</div>
    </div>
  )
}
