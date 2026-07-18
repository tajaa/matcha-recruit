import { ArrowLeft, ArrowRight } from 'lucide-react'

import { QUESTIONS } from '../auditRules'
import type { AuditAnswer } from '../auditRules'
import type { Theme } from './theme'

export function Questions(props: {
  t: Theme
  idx: number; setIdx: (n: number) => void
  answers: Record<string, AuditAnswer>
  setAnswer: (id: string, a: AuditAnswer) => void
  onFinish: () => void
  allAnswered: boolean
}) {
  const { t } = props
  const q = QUESTIONS[props.idx]
  const progress = ((props.idx + 1) / QUESTIONS.length) * 100

  return (
    <>
      <div className="mb-8">
        <p className="text-xs uppercase tracking-wider mb-2" style={{ color: t.muted }}>
          Step 2 of 2 &middot; Question {props.idx + 1} of {QUESTIONS.length}
        </p>
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ backgroundColor: t.progressBg }}
        >
          <div
            className="h-full transition-all"
            style={{ width: `${progress}%`, backgroundColor: t.ink }}
          />
        </div>
      </div>

      <article
        className="p-8 rounded-2xl mb-8"
        style={{ border: `1px solid ${t.line}` }}
      >
        <p className="text-xs uppercase tracking-wider mb-3" style={{ color: t.muted }}>
          {q.category}
        </p>
        <h2
          className="text-2xl mb-4"
          style={{ fontFamily: t.display, fontWeight: 500, color: t.ink, lineHeight: 1.3 }}
        >
          {q.question}
        </h2>
        {q.helper && (
          <p className="text-sm mb-6" style={{ color: t.muted }}>{q.helper}</p>
        )}

        <div className="grid grid-cols-3 gap-3">
          {(['yes', 'no', 'unsure'] as AuditAnswer[]).map(a => {
            const selected = props.answers[q.id] === a
            return (
              <button
                key={a}
                onClick={() => props.setAnswer(q.id, a)}
                className="h-12 rounded-lg text-sm font-medium capitalize transition-colors"
                style={selected ? t.selectedBtn : { backgroundColor: 'transparent', color: t.ink, border: `1px solid ${t.line}` }}
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
          style={{ color: t.ink }}
        >
          <ArrowLeft className="w-4 h-4" /> Previous
        </button>

        {props.idx === QUESTIONS.length - 1 ? (
          <button
            onClick={props.onFinish}
            disabled={!props.allAnswered}
            className="inline-flex items-center gap-2 px-6 h-11 rounded-full text-sm font-medium disabled:opacity-50"
            style={t.btnPrimary}
          >
            See my report <ArrowRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => props.setIdx(Math.min(QUESTIONS.length - 1, props.idx + 1))}
            className="inline-flex items-center gap-2 text-sm transition-opacity hover:opacity-60"
            style={{ color: t.ink }}
          >
            Next <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </>
  )
}
