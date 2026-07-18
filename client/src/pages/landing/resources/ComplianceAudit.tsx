import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/marketing/PricingContactModal'
import { api } from '../../../api/client'
import {
  INDUSTRIES,
  QUESTIONS,
  computeFindings,
  computeScore,
} from './auditRules'
import type { AuditAnswer } from './auditRules'
import { mkT } from './ComplianceAudit/theme'
import type { Step } from './ComplianceAudit/theme'
import { Intro } from './ComplianceAudit/Intro'
import { Context } from './ComplianceAudit/Context'
import { Questions } from './ComplianceAudit/Questions'
import { Results } from './ComplianceAudit/Results'

export default function ComplianceAudit({ embedded }: { embedded?: boolean }) {
  const [step, setStep] = useState<Step>('intro')
  const [stateSlug, setStateSlug] = useState('')
  const [headcount, setHeadcount] = useState<number | ''>('')
  const [industry, setIndustry] = useState<string>(INDUSTRIES[0])
  const [answers, setAnswers] = useState<Record<string, AuditAnswer>>({})
  const [questionIdx, setQuestionIdx] = useState(0)
  const [showPricing, setShowPricing] = useState(false)

  const [emailing, setEmailing] = useState(false)
  const [emailDone, setEmailDone] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  useEffect(() => {
    document.title = 'HR Compliance Audit — Matcha'
  }, [])

  const findings = useMemo(() => (step === 'results' ? computeFindings(answers) : []), [step, answers])
  const score = useMemo(() => (step === 'results' ? computeScore(answers) : null), [step, answers])
  const allAnswered = QUESTIONS.every(q => answers[q.id])

  const t = mkT(embedded)

  const setAnswer = (id: string, a: AuditAnswer) => {
    setAnswers(prev => ({ ...prev, [id]: a }))
    if (questionIdx < QUESTIONS.length - 1) {
      setTimeout(() => setQuestionIdx(i => Math.min(i + 1, QUESTIONS.length - 1)), 150)
    }
  }

  const submitEmail = async () => {
    setEmailing(true)
    setEmailError(null)
    try {
      await api.post('/resources/audit', {
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

  const root = embedded ? '/app/resources' : '/resources'

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6 pb-8' : 'pt-28 pb-20'} max-w-[820px] mx-auto px-6 sm:px-10`}>
        <nav className={`flex items-center gap-2 text-xs mb-8 ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          <Link to={root} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Resources</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <span className={embedded ? 'text-vsc-text/60' : ''} style={embedded ? undefined : { color: t.ink }}>Compliance Audit</span>
        </nav>

        {step === 'intro' && <Intro t={t} embedded={embedded} onStart={() => setStep('context')} />}

        {step === 'context' && (
          <Context
            t={t}
            embedded={embedded}
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
            t={t}
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
            t={t}
            embedded={embedded}
            score={score.score}
            findings={findings}
            stateSlug={stateSlug}
            root={root}
            emailing={emailing}
            emailError={emailError}
            emailDone={emailDone}
            onEmail={submitEmail}
            onRestart={() => {
              setStep('intro')
              setAnswers({})
              setQuestionIdx(0)
              setEmailDone(false)
              setEmailError(null)
            }}
            onSeePricing={() => setShowPricing(true)}
          />
        )}
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
