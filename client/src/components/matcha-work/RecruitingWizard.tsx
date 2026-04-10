import { useState } from 'react'
import {
  FileText, Upload, Mic, Trophy,
  Sparkles, ChevronRight, ChevronLeft,
  Bot, BarChart3, Briefcase,
} from 'lucide-react'

interface RecruitingWizardProps {
  onDismiss: () => void
  onStartHiring: () => void
}

const c = {
  bg: '#1e1e1e', cardBg: '#252526', border: '#333', text: '#d4d4d4',
  heading: '#e8e8e8', muted: '#6a737d', accent: '#ce9178', hoverBg: '#2a2d2e',
  green: '#22c55e',
}

export default function RecruitingWizard({ onDismiss, onStartHiring }: RecruitingWizardProps) {
  const [step, setStep] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const [direction, setDirection] = useState<'forward' | 'back'>('forward')

  const totalSteps = 4

  function goNext() {
    if (step === totalSteps - 1) {
      onStartHiring()
      return
    }
    setDirection('forward')
    setLeaving(true)
    setTimeout(() => {
      setStep((s) => s + 1)
      setLeaving(false)
    }, 200)
  }

  function goBack() {
    if (step === 0) return
    setDirection('back')
    setLeaving(true)
    setTimeout(() => {
      setStep((s) => s - 1)
      setLeaving(false)
    }, 200)
  }

  const transitionClass = leaving
    ? direction === 'forward'
      ? 'opacity-0 translate-x-4'
      : 'opacity-0 -translate-x-4'
    : 'opacity-100 translate-x-0'

  return (
    <div className="w-full max-w-lg mx-4">
      {/* Step indicators */}
      <div className="flex items-center justify-center gap-2 mb-8">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <button
            key={i}
            onClick={() => {
              if (i === step) return
              setDirection(i > step ? 'forward' : 'back')
              setLeaving(true)
              setTimeout(() => { setStep(i); setLeaving(false) }, 200)
            }}
            className="rounded-full transition-all duration-300"
            style={{
              width: i === step ? 28 : 8,
              height: 8,
              background: i === step ? c.accent : i < step ? c.green : '#444',
              cursor: 'pointer',
            }}
          />
        ))}
      </div>

      {/* Step content with transition */}
      <div
        className={`transition-all duration-200 ease-in-out ${transitionClass}`}
      >
        {step === 0 && <StepWelcome />}
        {step === 1 && <StepDescribe />}
        {step === 2 && <StepHowItWorks />}
        {step === 3 && <StepGetStarted />}
      </div>

      {/* Step counter */}
      <p className="text-center text-[10px] mt-6 mb-4" style={{ color: c.muted }}>
        Step {step + 1} of {totalSteps}
      </p>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={onDismiss}
          className="text-xs transition-colors hover:underline"
          style={{ color: c.muted }}
        >
          Skip
        </button>
        <div className="flex gap-2">
          {step > 0 && (
            <button
              onClick={goBack}
              className="px-4 py-2 text-xs font-medium rounded-lg transition-colors flex items-center gap-1"
              style={{ color: c.text, background: '#333' }}
            >
              <ChevronLeft size={12} />
              Back
            </button>
          )}
          <button
            onClick={goNext}
            className="px-5 py-2 text-xs font-medium rounded-lg transition-colors flex items-center gap-1"
            style={{ background: step === totalSteps - 1 ? c.green : c.accent, color: '#fff' }}
          >
            {step === totalSteps - 1 ? 'Start Hiring' : 'Next'}
            {step < totalSteps - 1 && <ChevronRight size={12} />}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Step 1: Welcome ── */

function StepWelcome() {
  const features = [
    { icon: Bot, label: 'AI Job Posting', desc: 'Chat creates structured postings' },
    { icon: BarChart3, label: 'Smart Screening', desc: 'AI ranks and scores resumes' },
    { icon: Briefcase, label: 'Full Pipeline', desc: 'Interview to offer in one place' },
  ]

  return (
    <div className="rounded-xl border p-6" style={{ background: c.cardBg, borderColor: c.border }}>
      <div className="flex justify-center mb-4">
        <div className="p-3 rounded-full" style={{ background: c.accent + '20' }}>
          <Sparkles size={28} style={{ color: c.accent }} />
        </div>
      </div>

      <h2 className="text-center text-lg font-semibold mb-2" style={{ color: c.heading }}>
        Let's set up your recruiting pipeline.
      </h2>
      <p className="text-center text-sm leading-relaxed mb-6" style={{ color: c.muted }}>
        Matcha Work helps you post roles, screen resumes with AI, conduct voice interviews, and
        build a shortlist — all in one workspace.
      </p>

      <div className="grid grid-cols-3 gap-3">
        {features.map((f) => (
          <div
            key={f.label}
            className="rounded-lg p-3 text-center"
            style={{ background: c.bg, border: `1px solid ${c.border}` }}
          >
            <f.icon size={20} className="mx-auto mb-2" style={{ color: c.accent }} />
            <p className="text-xs font-medium mb-0.5" style={{ color: c.heading }}>{f.label}</p>
            <p className="text-[10px] leading-snug" style={{ color: c.muted }}>{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Step 2: Describe the role ── */

function StepDescribe() {
  return (
    <div className="rounded-xl border p-6" style={{ background: c.cardBg, borderColor: c.border }}>
      <div className="flex justify-center mb-4">
        <div className="p-3 rounded-full" style={{ background: c.accent + '20' }}>
          <FileText size={28} style={{ color: c.accent }} />
        </div>
      </div>

      <h2 className="text-center text-lg font-semibold mb-2" style={{ color: c.heading }}>
        Describe the role
      </h2>
      <p className="text-center text-sm leading-relaxed mb-5" style={{ color: c.muted }}>
        Describe the role you're hiring for. Include title, location, salary range, and key
        requirements. Our AI will generate a structured job posting from your description.
      </p>

      {/* Example prompt preview */}
      <div
        className="rounded-lg p-4 text-sm leading-relaxed italic"
        style={{ background: c.bg, border: `1px dashed ${c.border}`, color: '#888' }}
      >
        "We're looking for a Senior Frontend Engineer in San Francisco, $150-180k. Must have 5+
        years React/TypeScript, experience with design systems, and strong communication skills.
        Remote-friendly, reports to VP of Engineering..."
      </div>

      <p className="text-center text-[11px] mt-4" style={{ color: c.muted }}>
        You'll type this into the chat in the next step.
      </p>
    </div>
  )
}

/* ── Step 3: How it works ── */

function StepHowItWorks() {
  const flow = [
    {
      icon: FileText,
      num: '1',
      title: 'Chat creates your posting',
      desc: 'AI structures your description into a job posting with sections for requirements, responsibilities, and benefits.',
    },
    {
      icon: Upload,
      num: '2',
      title: 'Upload resumes',
      desc: 'Drag & drop PDF resumes into the chat. AI extracts candidate info, skills, and experience automatically.',
    },
    {
      icon: Mic,
      num: '3',
      title: 'Voice interviews',
      desc: 'Gemini conducts screening interviews automatically. Candidates get an email link — no account needed.',
    },
    {
      icon: Trophy,
      num: '4',
      title: 'Review & hire',
      desc: 'AI shortlist with match scores. Compare candidates side-by-side and generate offer letters.',
    },
  ]

  return (
    <div className="rounded-xl border p-6" style={{ background: c.cardBg, borderColor: c.border }}>
      <h2 className="text-center text-lg font-semibold mb-5" style={{ color: c.heading }}>
        How it works
      </h2>

      <div className="space-y-3">
        {flow.map((item, i) => (
          <div key={i} className="flex items-start gap-3">
            {/* Numbered circle */}
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold"
              style={{ background: c.accent + '20', color: c.accent }}
            >
              {item.num}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <item.icon size={14} style={{ color: c.accent }} />
                <p className="text-sm font-medium" style={{ color: c.heading }}>{item.title}</p>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: c.muted }}>{item.desc}</p>
            </div>
          </div>
        ))}

        {/* Connecting line visual between steps */}
      </div>
    </div>
  )
}

/* ── Step 4: Get started ── */

function StepGetStarted() {
  return (
    <div className="rounded-xl border p-6 text-center" style={{ background: c.cardBg, borderColor: c.border }}>
      <div className="flex justify-center mb-4">
        <div className="p-4 rounded-full" style={{ background: c.green + '20' }}>
          <Sparkles size={32} style={{ color: c.green }} />
        </div>
      </div>

      <h2 className="text-lg font-semibold mb-2" style={{ color: c.heading }}>
        Your workspace is ready.
      </h2>
      <p className="text-sm leading-relaxed mb-4" style={{ color: c.muted }}>
        Start by describing the role in the chat below. The AI will create a structured job posting
        that you can review and refine in the pipeline panel on the right.
      </p>

      <div
        className="rounded-lg p-3 flex items-center gap-3 text-left"
        style={{ background: c.bg, border: `1px solid ${c.border}` }}
      >
        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: c.green }} />
        <p className="text-xs" style={{ color: c.text }}>
          Tip: After the posting is drafted, click <strong style={{ color: c.accent }}>"Add to Project"</strong> on
          any chat message to add it as a posting section.
        </p>
      </div>
    </div>
  )
}
