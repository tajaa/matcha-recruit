import { Link } from 'react-router-dom'
import { Mail } from 'lucide-react'

import { QUESTIONS } from '../auditRules'
import type { Finding } from '../auditRules'
import { SEVERITY_BG, SEVERITY_COLOR } from './constants'
import type { Theme } from './theme'

export function Results(props: {
  t: Theme
  embedded?: boolean
  score: number
  findings: Finding[]
  stateSlug: string
  root: string
  emailing: boolean; emailError: string | null; emailDone: boolean
  onEmail: () => void
  onRestart: () => void
  onSeePricing: () => void
}) {
  const { t, embedded } = props
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
        <p className={`text-xs uppercase tracking-wider mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Your Gap Report</p>
        <h2
          className={embedded ? "text-2xl font-semibold text-vsc-text" : "text-4xl sm:text-5xl tracking-tight"}
          style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
        >
          Compliance score: {props.score}/100
        </h2>
        <p className="mt-3 text-lg" style={{ color: gradeColor, fontFamily: embedded ? 'inherit' : t.display }}>
          {grade}
        </p>
      </header>

      <div className="grid grid-cols-3 gap-3 mb-10">
        <ScoreBox t={t} label="High severity" n={high.length} color="#c1543a" />
        <ScoreBox t={t} label="Medium" n={med.length} color="#c19f3a" />
        <ScoreBox t={t} label="Low / clear" n={low.length || (QUESTIONS.length - props.findings.length)} color="#5a8c5a" />
      </div>

      {props.findings.length > 0 ? (
        <section className="mb-12">
          <h3
            className="text-2xl mb-6"
            style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
          >
            Flagged Gaps ({props.findings.length})
          </h3>
          <div className="flex flex-col gap-3">
            {props.findings.map(f => (
              <article
                key={f.id}
                className="p-5 rounded-xl"
                style={{
                  border: `1px solid ${t.line}`,
                  backgroundColor: SEVERITY_BG[f.severity],
                  borderLeft: `3px solid ${SEVERITY_COLOR[f.severity]}`,
                }}
              >
                <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
                  <h4 className="text-base" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
                    {f.title}
                  </h4>
                  <span
                    className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded"
                    style={{ color: SEVERITY_COLOR[f.severity], border: `1px solid ${SEVERITY_COLOR[f.severity]}` }}
                  >
                    {f.severity}
                  </span>
                </div>
                <p className="text-xs uppercase tracking-wider mb-2" style={{ color: t.muted }}>
                  {f.category}
                </p>
                <p className="text-sm" style={{ color: t.ink, opacity: 0.85, lineHeight: 1.6 }}>
                  {f.detail}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : (
        <section
          className="mb-12 p-8 rounded-xl text-center"
          style={{ border: `1px solid ${t.line}`, backgroundColor: SEVERITY_BG.low }}
        >
          <h3 className="text-xl" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            No gaps flagged.
          </h3>
          <p className="mt-2 text-sm" style={{ color: t.muted }}>
            Strong compliance posture. Re-run quarterly as laws change.
          </p>
        </section>
      )}

      <section
        className="p-6 rounded-2xl mb-8"
        style={{ border: `1px solid ${t.line}` }}
      >
        <h3 className="text-xl mb-2" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
          Email yourself a copy
        </h3>
        <p className="text-sm mb-5" style={{ color: t.muted }}>
          We'll send the full gap report to your account email so you can
          share with your team or revisit later.
        </p>
        {props.emailDone ? (
          <p className="text-sm" style={{ color: '#5a8c5a' }}>
            Sent. Check your inbox.
          </p>
        ) : (
          <button
            onClick={props.onEmail}
            disabled={props.emailing}
            className="inline-flex items-center justify-center gap-2 px-5 h-11 rounded-full text-sm font-medium disabled:opacity-50"
            style={t.btnPrimary}
          >
            <Mail className="w-4 h-4" />
            {props.emailing ? 'Sending…' : 'Email me a copy'}
          </button>
        )}
        {props.emailError && (
          <p className="text-sm mt-2" style={{ color: '#c1543a' }}>{props.emailError}</p>
        )}
      </section>

      <section
        className="p-8 rounded-2xl mb-8"
        style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
      >
        <h3 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
          Close these gaps with Matcha
        </h3>
        <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
          Matcha generates the missing policies, tracks every state and
          local rule, and re-runs your audit automatically as laws change
          — so the score above doesn't quietly slip.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={props.onSeePricing}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={t.btnPrimary}
          >
            See Matcha →
          </button>
          {props.stateSlug && (
            <Link
              to={`${props.root}/states/${props.stateSlug}`}
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={t.btnSecondary}
            >
              View {props.stateSlug.replace(/-/g, ' ')} requirements
            </Link>
          )}
          <button
            onClick={props.onRestart}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={t.btnSecondary}
          >
            Restart audit
          </button>
        </div>
      </section>

      <p className="text-xs" style={{ color: t.muted }}>
        This audit is informational only and not legal advice. Consult
        employment counsel for your specific situation.
      </p>
    </>
  )
}

function ScoreBox({ t, label, n, color }: { t: Theme; label: string; n: number; color: string }) {
  return (
    <div
      className="p-5 rounded-xl text-center"
      style={{ border: `1px solid ${t.line}` }}
    >
      <div
        className="text-4xl mb-1"
        style={{ fontFamily: t.display, fontWeight: 500, color }}
      >
        {n}
      </div>
      <div className="text-xs" style={{ color: t.muted }}>{label}</div>
    </div>
  )
}
