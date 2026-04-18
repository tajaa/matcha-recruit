import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { invalidateMeCache } from '../../hooks/useMe'
import {
  MessageSquare,
  FolderKanban,
  Presentation,
  Languages,
  UserPlus,
  Hash,
  Rocket,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Mic,
  Users,
  BriefcaseBusiness,
} from 'lucide-react'

const STORAGE_KEY = 'mw-onboarding-complete'

interface OnboardingWizardProps {
  onDismiss: () => void
}

interface Step {
  title: string
  description: string
  extra?: string
  icon: React.ReactNode
  badges?: { label: string; icon: React.ReactNode }[]
}

const steps: Step[] = [
  {
    title: 'Welcome to Matcha Work',
    description:
      'Your AI-powered workspace for research, documents, and collaboration.',
    icon: <Sparkles size={48} className="text-emerald-400" />,
  },
  {
    title: 'Threads',
    description:
      'Start a chat thread to research any topic. The AI assistant helps with HR questions, compliance, document drafting, and more.',
    icon: <MessageSquare size={48} className="text-emerald-400" />,
    badges: [
      { label: 'Chat', icon: <MessageSquare size={14} /> },
      { label: 'Projects', icon: <FolderKanban size={14} /> },
      { label: 'Presentations', icon: <Presentation size={14} /> },
    ],
  },
  {
    title: 'Language Tutor',
    description:
      'Practice English, Spanish, or French with an AI voice tutor. Get real-time grammar corrections and a proficiency analysis when you\'re done.',
    icon: <Languages size={48} className="text-emerald-400" />,
    badges: [
      { label: 'Voice Practice', icon: <Mic size={14} /> },
      { label: 'Grammar Feedback', icon: <Sparkles size={14} /> },
    ],
  },
  {
    title: 'Projects',
    description:
      'Create projects to organize work. Recruiting projects include a full hiring pipeline \u2014 post roles, upload resumes, AI-rank candidates, and conduct voice interviews.',
    icon: <FolderKanban size={48} className="text-emerald-400" />,
    badges: [
      { label: 'Research', icon: <FolderKanban size={14} /> },
      { label: 'Recruiting', icon: <BriefcaseBusiness size={14} /> },
      { label: 'Presentations', icon: <Presentation size={14} /> },
    ],
  },
  {
    title: 'Collaborate',
    description:
      'Invite people to your threads for real-time collaboration. Both of you can query the AI together and see responses live.',
    extra: 'Use the Invite button on any thread, or visit the People page to manage connections.',
    icon: <UserPlus size={48} className="text-emerald-400" />,
    badges: [
      { label: 'Invite', icon: <UserPlus size={14} /> },
      { label: 'Connections', icon: <Users size={14} /> },
    ],
  },
  {
    title: 'Channels',
    description:
      'Join or create channels to communicate with your team. Paid creator channels are available for verified accounts.',
    icon: <Hash size={48} className="text-emerald-400" />,
  },
  {
    title: "You're all set!",
    description: 'Start by creating a new thread.',
    icon: <Rocket size={48} className="text-emerald-400" />,
  },
]

function markCompleted() {
  // Write to both localStorage and sessionStorage. Some browsers (Safari in
  // private mode, ITP in strict mode, some corporate profiles) block or wipe
  // localStorage silently, which was causing the wizard to reappear on every
  // load. Writing to both gives us a fallback, and the try/catch prevents a
  // storage failure from breaking the dismiss flow.
  try {
    localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    /* ignore — see sessionStorage fallback below */
  }
  try {
    sessionStorage.setItem(STORAGE_KEY, '1')
  } catch {
    /* ignore */
  }
  // Persist server-side so the flag survives storage wipes, browser changes, and device switches.
  api.post('/auth/work-onboarded').then(() => invalidateMeCache()).catch(() => {})
}

export default function OnboardingWizard({ onDismiss }: OnboardingWizardProps) {
  const [step, setStep] = useState(0)
  const current = steps[step]
  const isLast = step === steps.length - 1

  // As soon as the wizard is shown, mark it as "seen". This prevents the
  // most common repeat-popup case: user clicks Next a few times, closes the
  // tab without reaching the final step, and then sees the wizard again next
  // session because finish() was never called. If the user specifically wants
  // to replay the tour later, we can add a "Reset tour" settings option.
  useEffect(() => {
    markCompleted()
  }, [])

  function finish() {
    markCompleted()
    onDismiss()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
        {/* Step dots */}
        <div className="flex justify-center gap-1.5 pt-5 pb-2">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === step
                  ? 'w-6 bg-emerald-500'
                  : i < step
                    ? 'w-1.5 bg-emerald-700'
                    : 'w-1.5 bg-zinc-700'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="px-8 py-8 flex flex-col items-center text-center min-h-[320px] justify-center">
          <div className="mb-6 p-4 rounded-2xl bg-zinc-800/60 border border-zinc-700/50">
            {current.icon}
          </div>
          <h2 className="text-xl font-semibold text-white mb-3">
            {current.title}
          </h2>
          <p className="text-zinc-400 text-sm leading-relaxed max-w-sm">
            {current.description}
          </p>
          {current.extra && (
            <p className="text-zinc-500 text-xs leading-relaxed max-w-sm mt-2">
              {current.extra}
            </p>
          )}
          {current.badges && (
            <div className="flex flex-wrap justify-center gap-2 mt-5">
              {current.badges.map((b) => (
                <span
                  key={b.label}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-800 border border-zinc-700 text-xs text-zinc-300"
                >
                  {b.icon}
                  {b.label}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-8 pb-6 flex items-center justify-between">
          {step > 0 ? (
            <button
              onClick={() => setStep(step - 1)}
              className="flex items-center gap-1 text-sm text-zinc-400 hover:text-white transition-colors"
            >
              <ChevronLeft size={16} />
              Back
            </button>
          ) : (
            <button
              onClick={finish}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Skip
            </button>
          )}
          {isLast ? (
            <button
              onClick={finish}
              className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Start Working
            </button>
          ) : (
            <button
              onClick={() => setStep(step + 1)}
              className="flex items-center gap-1 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Next
              <ChevronRight size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export { STORAGE_KEY as ONBOARDING_STORAGE_KEY }
