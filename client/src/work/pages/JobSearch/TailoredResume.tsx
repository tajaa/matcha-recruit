import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Loader2, Pencil } from 'lucide-react'
import type { JobLeadDetail, TailoredLine, TailoredResume as Tailored } from '../../api/matchaWork/jobSearch'
import { isTailoring, resumeFileName } from './jobSearchLogic'

/**
 * Their résumé, tailored to this job, to read before they apply. The server
 * rewrites only what is already in their saved résumé and drops any line it
 * can't trace to it; each line here opens to the résumé lines it came from.
 * What the posting asks for that the résumé doesn't show is listed apart,
 * never written in. Edits stay on this page (Copy or Download takes them);
 * nothing is sent or submitted.
 */
export default function TailoredResumeSection({ lead, busy, resumePath, onTailor }: {
  lead: JobLeadDetail
  busy: boolean
  /** Where their saved résumé is kept and edited (Tasks → Résumé). */
  resumePath: string
  onTailor: (leadId: string) => void
}) {
  const tailoring = isTailoring(lead)
  const tailored = lead.tailored_resume?.experience?.length ? lead.tailored_resume : null
  return (
    <section className="space-y-2">
      <div className="flex items-center">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">Your résumé for this job</h3>
        {!tailoring && (
          <button
            type="button"
            onClick={() => onTailor(lead.id)}
            disabled={busy}
            className="ml-auto text-[11px] font-semibold text-w-accent hover:underline disabled:opacity-40"
          >
            {tailored ? 'Tailor again' : 'Tailor my résumé'}
          </button>
        )}
      </div>
      {tailoring ? (
        <p className="flex items-center gap-1.5 text-[11px] text-w-dim">
          <Loader2 size={12} className="animate-spin" />Rewriting your résumé for this posting…
        </p>
      ) : tailored ? (
        // Keyed by when it was made, so a new version starts without old edits.
        <TailoredBody key={tailored.made_at ?? 'tailored'} lead={lead} tailored={tailored} resumePath={resumePath} />
      ) : (
        <p className="text-[11px] leading-4 text-w-dim">
          {lead.resume_status === 'failed'
            ? "Tailoring didn't finish for this job. Try again. "
            : "Rewrites your saved résumé for this posting, using only what's already in it, so you can read it before you apply. "}
          <Link to={resumePath} className="text-w-accent hover:underline">Your résumé</Link>
        </p>
      )}
    </section>
  )
}

function TailoredBody({ lead, tailored, resumePath }: { lead: JobLeadDetail; tailored: Tailored; resumePath: string }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(tailored.text)
  const [copied, setCopied] = useState(false)
  const saved = tailored.resume_saved_at ? new Date(tailored.resume_saved_at).toLocaleDateString() : null

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = resumeFileName(lead)
    link.click()
    URL.revokeObjectURL(url)
  }

  const action = 'inline-flex items-center gap-1 text-[11px] font-semibold text-w-accent hover:underline'
  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-4 text-w-dim">
        Made from <Link to={resumePath} className="text-w-accent hover:underline">your résumé</Link>
        {saved ? ` saved ${saved}` : ''}. Every line comes from it; nothing was added.
        {tailored.dropped > 0 && ` ${tailored.dropped} ${tailored.dropped === 1 ? 'line was' : 'lines were'} left out because ${tailored.dropped === 1 ? "it didn't" : "they didn't"} match your résumé.`}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => void copy()} className={action}>{copied ? 'Copied' : 'Copy'}</button>
        <button type="button" onClick={download} className={action}><Download size={11} />Download</button>
        <button type="button" onClick={() => setEditing((v) => !v)} className={action}>
          <Pencil size={11} />{editing ? 'Done editing' : 'Edit'}
        </button>
      </div>
      {editing ? (
        <div className="space-y-1">
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); setCopied(false) }}
            rows={18}
            aria-label="Your tailored résumé"
            className="w-full resize-y rounded-md border border-w-line bg-w-surface2/50 px-2.5 py-1.5 font-mono text-[11px] leading-5 text-w-text outline-none focus:border-w-accent/60"
          />
          <p className="text-[11px] text-w-dim">Your edits aren't saved: Copy or Download them before you leave this job.</p>
        </div>
      ) : (
        <div className="space-y-3 rounded-lg bg-w-surface2/60 p-3">
          {tailored.summary.text && <p className="select-text text-xs leading-5 text-w-text">{tailored.summary.text}</p>}
          {tailored.experience.map((role, i) => (
            <div key={`${role.organization}-${role.role}-${i}`} className="space-y-1">
              <p className="text-xs font-semibold text-w-text">
                {[role.role, role.organization].filter(Boolean).join(' — ')}
                {role.dates && <span className="font-normal text-w-dim"> · {role.dates}</span>}
              </p>
              {role.bullets.map((line, j) => <Line key={j} line={line} />)}
            </div>
          ))}
          {tailored.skills.length > 0 && (
            <p className="text-[11px] leading-5 text-w-text"><span className="font-semibold">Skills </span>{tailored.skills.join(', ')}</p>
          )}
          {tailored.sections.map((section) => (
            <div key={section.heading} className="space-y-1">
              <p className="text-xs font-semibold text-w-text">{section.heading}</p>
              {section.lines.map((line, j) => <Line key={j} line={line} />)}
            </div>
          ))}
        </div>
      )}
      {tailored.changes.length > 0 && (
        <div className="space-y-1">
          <p className="pt-1 text-[11px] font-semibold text-w-text">What changed for this job</p>
          {tailored.changes.map((change) => <p key={change} className="text-[11px] leading-4 text-w-dim">• {change}</p>)}
        </div>
      )}
      {tailored.gaps.length > 0 && (
        <div className="space-y-1">
          <p className="pt-1 text-[11px] font-semibold text-w-text">The posting asks for, your résumé doesn't show</p>
          {tailored.gaps.map((gap) => <p key={gap} className="text-[11px] leading-4 text-w-dim">• {gap}</p>)}
          <p className="text-[11px] text-w-faint">Add these only if they're true.</p>
        </div>
      )}
    </div>
  )
}

/** One rewritten line; it opens to the résumé lines it came from. */
function Line({ line }: { line: TailoredLine }) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-start gap-1.5 text-xs leading-5 text-w-text">
        <span className="w-3 shrink-0 text-[11px] text-w-dim">•</span>
        <span className="select-text">{line.text}</span>
      </summary>
      <p className="pl-[18px] text-[11px] italic leading-4 text-w-dim">
        From your résumé: {line.sources.map((source) => `“${source}”`).join(' ')}
      </p>
    </details>
  )
}
