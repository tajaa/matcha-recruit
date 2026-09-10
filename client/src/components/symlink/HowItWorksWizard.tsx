import { useState } from 'react'
import { Check, ChevronLeft, ChevronRight, KeyRound, MessageSquare, Plus, Send, ShieldCheck, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { writeHowItWorksDismissed } from './howItWorksStorage'

// Step-through explainer for the sym-links page. Content mirrors what the
// feature actually does — the passcode really is withheld from the invite
// email, and completion really is decided server-side from the link's spec, so
// don't soften either line into "the assistant decides when it's done".

type Step = {
  icon: typeof KeyRound
  title: string
  body: React.ReactNode
}

const STEPS: Step[] = [
  {
    icon: Plus,
    title: 'You create the request',
    body: (
      <>
        <p>
          Pick what you need: a <strong>credential or document</strong>, a <strong>manager review</strong>, an{' '}
          <strong>info update</strong>, or a <strong>custom checklist</strong> you define yourself.
        </p>
        <p>
          Each kind already knows what it has to collect. Add or edit items if you want, mark them required or
          optional, and name who it is going to.
        </p>
        <p className="text-slate-500">
          For a credential upload, link the request to an employee. That is who the document gets filed under when
          you approve it.
        </p>
      </>
    ),
  },
  {
    icon: KeyRound,
    title: 'They open it with your passcode',
    body: (
      <>
        <p>
          The recipient gets their own single-purpose link. To open it they enter your company passcode, which you
          will find under <Link to="/app/symlink/settings" className="font-medium text-emerald-700 underline">Passcode</Link>.
        </p>
        <p>
          <strong>The passcode is deliberately left out of the invite email.</strong> Send it another way — in
          person, by text, or posted in your team channel. An emailed link that carries its own key is not a
          second factor.
        </p>
        <p className="text-slate-500">
          It rotates weekly. Someone already working in a link is not kicked out when it changes.
        </p>
      </>
    ),
  },
  {
    icon: MessageSquare,
    title: 'A guided chat collects everything',
    body: (
      <>
        <p>
          Instead of a form they can half-fill, the link asks one question at a time and keeps going until it has
          everything: dates, numbers, notes, and any files.
        </p>
        <p>
          <strong>It cannot finish early.</strong> Whether the request is complete is decided by your spec on the
          server, not by the assistant — so a missing expiry date or an unattached document stops it from being
          sent.
        </p>
        <p className="text-slate-500">
          The last screen shows them everything they gave you, fully editable, before anything reaches you.
        </p>
      </>
    ),
  },
  {
    icon: ShieldCheck,
    title: 'You review, then apply',
    body: (
      <>
        <p>
          A submission arrives as <strong>Needs review</strong>. Nothing has been written to your records yet.
        </p>
        <p>
          Approving it is what commits: a credential is filed to that employee, an info update patches their
          phone, address, or emergency contact, and a review or custom request is kept as a record. Or reject it
          with a note explaining what was wrong.
        </p>
        <p className="text-slate-500">
          Links expire on their own, and you can resend or revoke one at any time from its detail page.
        </p>
      </>
    ),
  },
]

export function HowItWorksWizard({ onClose, onCreate }: { onClose: () => void; onCreate?: () => void }) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const Icon = current.icon
  const isLast = step === STEPS.length - 1

  function dismiss() {
    writeHowItWorksDismissed(true)
    onClose()
  }

  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-4 border-b border-emerald-100 bg-emerald-50/60 px-5 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">How sym-links work</p>
          <p className="mt-1 text-sm text-slate-600">Four steps, about a minute.</p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700"
        >
          <X size={18} />
        </button>
      </div>

      <div className="grid gap-6 px-5 py-6 sm:grid-cols-[auto_1fr]">
        <ol className="flex gap-4 sm:flex-col sm:gap-3" aria-label="Steps">
          {STEPS.map((s, i) => {
            const done = i < step
            const active = i === step
            return (
              <li key={s.title}>
                <button
                  type="button"
                  onClick={() => setStep(i)}
                  aria-current={active ? 'step' : undefined}
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition sm:w-56 ${
                    active ? 'bg-emerald-50 font-medium text-emerald-900' : 'text-slate-500 hover:bg-slate-50'
                  }`}
                >
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      active
                        ? 'bg-emerald-700 text-white'
                        : done
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {done ? <Check size={13} /> : i + 1}
                  </span>
                  <span className="hidden truncate sm:block">{s.title}</span>
                </button>
              </li>
            )
          })}
        </ol>

        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="rounded-xl bg-emerald-50 p-2 text-emerald-700">
              <Icon size={20} />
            </span>
            <h3 className="text-lg font-semibold text-slate-900">{current.title}</h3>
          </div>
          <div className="mt-3 space-y-3 text-sm leading-relaxed text-slate-700">{current.body}</div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-40"
            >
              <ChevronLeft size={16} /> Back
            </button>
            {isLast ? (
              <>
                {onCreate && (
                  <button
                    type="button"
                    onClick={() => {
                      writeHowItWorksDismissed(true)
                      onCreate()
                    }}
                    className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800"
                  >
                    <Send size={16} /> Create your first sym-link
                  </button>
                )}
                <button
                  type="button"
                  onClick={dismiss}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-slate-500 transition hover:text-slate-800"
                >
                  Got it
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
                className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
              >
                Next <ChevronRight size={16} />
              </button>
            )}
            <span className="ml-auto text-xs text-slate-400">
              Step {step + 1} of {STEPS.length}
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
