import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ChevronDown, ExternalLink, Link2, Loader2, Mail, MailOpen, Scale, Sparkles, X } from 'lucide-react'
import type { JobApproach, JobLeadDetail } from '../../api/matchaWork/jobSearch'
import {
  GMAIL_DRAFTS_URL, channelLabel, compParts, evidenceLabel, fitText, hostOf, isDrafting, isIrrelevant, partLine, placeholders,
  questionText, tidyPosting, usableApproach, webUrl,
} from './jobSearchLogic'

/**
 * One job: pay with the text it came from, how to approach it, and the drafts
 * (outreach, answers to the application's own questions, cover letter). Every
 * draft has Copy, and the first message can go to the person's Gmail drafts
 * (Draft email); nothing here sends or submits. Mirrors the macOS app's job pane.
 */
export default function LeadPane({
  lead, canDraft, busy, emailNotConnected, emailDrafted, emailPath, onClose, onSetState, onSaveNotes, onRedraft,
  onDraftEmail, onAskEspresso,
}: {
  lead: JobLeadDetail | null
  /** The search finished or was cancelled, so it can draft more approaches. */
  canDraft: boolean
  busy: boolean
  emailNotConnected: boolean
  /** Draft email just put this job's first message in Gmail drafts. */
  emailDrafted: boolean
  /** Where Gmail is connected (the Email page). */
  emailPath: string
  onClose: () => void
  onSetState: (state: string, leadId: string) => void
  onSaveNotes: (notes: string, leadId: string) => void
  onRedraft: () => void
  onDraftEmail: (leadId: string) => void
  onAskEspresso: (lead: JobLeadDetail) => void
}) {
  return (
    <aside className="fixed inset-0 z-40 flex flex-col bg-w-surface xl:static xl:z-auto xl:w-[440px] xl:shrink-0 xl:border-l xl:border-w-line">
      <div className="flex justify-end px-3 pt-2">
        <button type="button" onClick={onClose} aria-label="Close the job" className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text">
          <X size={14} />
        </button>
      </div>
      {lead ? (
        <LeadBody
          key={lead.id}
          lead={lead}
          canDraft={canDraft}
          busy={busy}
          emailNotConnected={emailNotConnected}
          emailDrafted={emailDrafted}
          emailPath={emailPath}
          onSetState={onSetState}
          onSaveNotes={onSaveNotes}
          onRedraft={onRedraft}
          onDraftEmail={onDraftEmail}
          onAskEspresso={onAskEspresso}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
      )}
    </aside>
  )
}

function LeadBody({
  lead, canDraft, busy, emailNotConnected, emailDrafted, emailPath, onSetState, onSaveNotes, onRedraft, onDraftEmail,
  onAskEspresso,
}: {
  lead: JobLeadDetail
  canDraft: boolean
  busy: boolean
  emailNotConnected: boolean
  emailDrafted: boolean
  emailPath: string
  onSetState: (state: string, leadId: string) => void
  onSaveNotes: (notes: string, leadId: string) => void
  onRedraft: () => void
  onDraftEmail: (leadId: string) => void
  onAskEspresso: (lead: JobLeadDetail) => void
}) {
  // Keyed by the job, so a different job starts from its own notes.
  const [notes, setNotes] = useState(lead.notes)
  const approach = usableApproach(lead.approach)
  const posting = webUrl(lead.apply_url ?? lead.source_url)
  const facts = [lead.company, lead.location, lead.remote === true ? 'Remote' : null, lead.posted_text]
    .filter((part): part is string => !!part)
  const parts = compParts(lead)
  const drafting = isDrafting(lead)

  return (
    <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pb-8">
      <div className="space-y-2">
        <h2 className="select-text text-base font-semibold text-w-text">{lead.title}</h2>
        <p className="text-[11px] text-w-dim">{facts.join(' · ')}</p>
        {(lead.fit_reasons.length > 0 || lead.fit_score != null) && (
          <p className="text-[11px] leading-5 text-w-dim">
            <span className="mr-1.5 rounded-full bg-w-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-w-text">Fit {fitText(lead.fit_score)}</span>
            {lead.fit_reasons.join(' · ')}
          </p>
        )}
        {isIrrelevant(lead) && lead.screen_reason && <p className="text-[11px] text-amber-500">Screened out: {lead.screen_reason}</p>}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          {posting && (
            <a href={posting} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-md bg-w-accent px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-w-accent-hi">
              <ExternalLink size={12} /> Open posting
            </a>
          )}
          <EmailButton lead={lead} approach={approach} busy={busy} onDraftEmail={onDraftEmail} />
        </div>
        {emailDrafted && (
          <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-w-dim">
            <CheckCircle2 size={12} className="text-emerald-500" />
            It's in your Gmail drafts, to edit and send.
            <a href={GMAIL_DRAFTS_URL} target="_blank" rel="noopener noreferrer" className="text-w-accent hover:underline">Open Gmail drafts</a>
          </p>
        )}
        {emailNotConnected && (
          <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-w-dim">
            <Mail size={12} className="text-amber-500" />
            Connect Gmail in Email first, then Draft email again.
            <Link to={emailPath} className="text-w-accent hover:underline">Open Email</Link>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <MarkMenu state={lead.user_state} disabled={busy} onPick={(state) => onSetState(state, lead.id)} />
          <button
            type="button"
            onClick={() => onAskEspresso(lead)}
            title="Work on this job with Espresso: outreach, answers, cover letter"
            className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2"
          >
            <Sparkles size={12} /> Ask Espresso
          </button>
        </div>
      </div>

      <Section title="Pay">
        {parts.length === 0 && <p className="text-xs text-w-text">This posting doesn't state pay.</p>}
        {parts.map(([name, part]) => {
          const evidenceUrl = webUrl(part.evidence?.url)
          return (
            <div key={name} className="space-y-1">
              <p className="flex items-baseline gap-2 text-xs text-w-text">
                <span className="w-14 shrink-0 text-[11px] font-semibold">{name}</span>
                {partLine(name, part)}
              </p>
              {part.evidence?.quote && (
                <p className="flex items-start gap-1 pl-16 text-[11px] italic leading-4 text-w-dim">
                  <span className="select-text">“{part.evidence.quote}”</span>
                  {evidenceUrl && (
                    <a href={evidenceUrl} target="_blank" rel="noopener noreferrer" title={evidenceLabel(part.evidence.origin)} aria-label={evidenceLabel(part.evidence.origin)} className="shrink-0 not-italic text-w-dim hover:text-w-text">
                      <Link2 size={11} />
                    </a>
                  )}
                </p>
              )}
            </div>
          )
        })}
        {lead.pay_law_hint && (
          <p className="flex items-start gap-1.5 text-[11px] text-w-dim"><Scale size={12} className="mt-0.5 shrink-0" />{lead.pay_law_hint}</p>
        )}
      </Section>

      <Section
        title="How to approach it"
        trailing={!drafting && canDraft && (
          <button type="button" onClick={onRedraft} disabled={busy} className="text-[11px] font-semibold text-w-accent hover:underline disabled:opacity-40">
            {approach ? 'Redraft' : 'Draft'}
          </button>
        )}
      >
        {drafting ? (
          <p className="flex items-center gap-1.5 text-[11px] text-w-dim"><Loader2 size={12} className="animate-spin" />Researching the company and drafting…</p>
        ) : approach ? (
          <ApproachBody approach={approach} />
        ) : (
          <p className="text-[11px] text-w-dim">
            {lead.approach_status === 'failed'
              ? "Drafting didn't finish for this job. Try Redraft."
              : 'Approaches are drafted for the top-ranked jobs. Draft one for this job any time.'}
          </p>
        )}
      </Section>

      <Section
        title="Your notes"
        trailing={notes !== lead.notes && (
          <button type="button" onClick={() => onSaveNotes(notes, lead.id)} disabled={busy} className="text-[11px] font-semibold text-w-accent hover:underline disabled:opacity-40">
            Save
          </button>
        )}
      >
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={4000}
          rows={3}
          aria-label="Your notes"
          className="w-full resize-y rounded-md border border-w-line bg-w-surface2/50 px-2.5 py-1.5 text-xs text-w-text outline-none focus:border-w-accent/60"
        />
      </Section>

      {lead.description && (
        <Section title="The posting">
          <p className="select-text whitespace-pre-wrap text-[11px] leading-5 text-w-text">{tidyPosting(lead.description)}</p>
        </Section>
      )}
    </div>
  )
}

/** The first message, into Gmail drafts: Draft email, then a way back to it
 *  while it waits there, then that it was sent. */
function EmailButton({ lead, approach, busy, onDraftEmail }: {
  lead: JobLeadDetail
  approach: JobApproach | null
  busy: boolean
  onDraftEmail: (leadId: string) => void
}) {
  if (!approach?.outreach?.body) return null
  const button = 'inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40'
  if (lead.email_sent_at) {
    return <span className="inline-flex items-center gap-1.5 text-[11px] text-w-dim"><CheckCircle2 size={12} /> Email sent</span>
  }
  if (lead.email_draft_id) {
    // Asked again, the server returns the same draft while it's in Gmail, or
    // makes a new one if it was sent or deleted there.
    return (
      <button type="button" onClick={() => onDraftEmail(lead.id)} disabled={busy} title="It's in your Gmail drafts: edit it and send it from Gmail" className={button}>
        <MailOpen size={12} /> Edit draft in Gmail
      </button>
    )
  }
  return (
    <button type="button" onClick={() => onDraftEmail(lead.id)} disabled={busy} title="Puts the first message in your Gmail drafts, to edit and send from Gmail. Nothing is sent." className={button}>
      <Mail size={12} /> Draft email
    </button>
  )
}

const STATES: [string, string][] = [['saved', 'Saved'], ['applied', 'Applied'], ['dismissed', 'Dismiss']]

function MarkMenu({ state, disabled, onPick }: { state: string; disabled: boolean; onPick: (state: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const pick = (next: string) => { setOpen(false); onPick(next) }
  const item = 'block w-full px-3 py-1.5 text-left text-[11px] text-w-text hover:bg-w-surface2'
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40"
      >
        {state === 'new' ? 'Mark…' : state.charAt(0).toUpperCase() + state.slice(1)}
        <ChevronDown size={11} />
      </button>
      {open && (
        <div role="menu" className="absolute left-0 top-full z-20 mt-1 w-32 overflow-hidden rounded-md border border-w-line bg-w-surface py-1 shadow-xl">
          {STATES.map(([value, label]) => (
            <button key={value} type="button" role="menuitem" onClick={() => pick(value)} className={item}>{label}</button>
          ))}
          {state !== 'new' && (
            <>
              <div className="my-1 border-t border-w-line" />
              <button type="button" role="menuitem" onClick={() => pick('new')} className={item}>Clear</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ApproachBody({ approach }: { approach: JobApproach }) {
  const outreach = approach.outreach
  const blanks = outreach?.body ? placeholders(`${outreach.subject ?? ''}\n${outreach.body}`) : []
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <span className="inline-block rounded-full bg-w-accent/15 px-2 py-0.5 text-[10px] font-semibold text-w-text">{channelLabel(approach.channel)}</span>
        {approach.summary && <p className="select-text text-xs leading-5 text-w-text">{approach.summary}</p>}
      </div>
      <Bullets title="Steps" items={approach.steps} numbered />
      <Bullets title="What to lead with" items={approach.talking_points} />
      <Bullets title="On pay" items={approach.negotiation} />
      {!!approach.contacts?.length && (
        <div className="space-y-1">
          <Subheading>People</Subheading>
          {approach.contacts.map((contact) => {
            const url = webUrl(contact.source_url)
            return (
              <p key={`${contact.name}-${contact.role ?? ''}`} className="flex items-center gap-1.5 text-xs">
                <span className="font-semibold text-w-text">{contact.name}</span>
                {contact.role && <span className="text-[11px] text-w-dim">{contact.role}</span>}
                {url && (
                  <a href={url} target="_blank" rel="noopener noreferrer" title="Where they're named" aria-label="Where they're named" className="text-w-dim hover:text-w-text">
                    <Link2 size={11} />
                  </a>
                )}
              </p>
            )
          })}
        </div>
      )}
      {outreach?.body && (
        <>
          <DraftBox
            title="First message"
            header={[outreach.to_email ? `To: ${outreach.to_email}` : null, outreach.subject ? `Subject: ${outreach.subject}` : null].filter(Boolean).join('\n')}
            text={outreach.body}
            copyText={`${outreach.subject ? `Subject: ${outreach.subject}\n\n` : ''}${outreach.body}`}
          />
          {blanks.length > 0 && (
            <p className="text-[11px] leading-4 text-w-dim">
              Fill in {blanks.join(', ')} before you send it. Draft email puts it in Gmail, where you can.
            </p>
          )}
        </>
      )}
      {!!approach.answers?.length && (
        <div className="space-y-2">
          <Subheading>Application answers</Subheading>
          {approach.answers.map((answer, i) => (
            <DraftBox key={`${answer.question_key ?? i}`} title={`${answer.question}${answer.likely ? '  (likely question)' : ''}`} text={answer.answer} copyText={answer.answer} />
          ))}
        </div>
      )}
      {!!approach.unanswered?.length && (
        <div className="space-y-1">
          <Subheading>Answer these yourself</Subheading>
          {approach.unanswered.map((q, i) => <p key={`${q.key ?? i}`} className="text-[11px] text-w-dim">• {questionText(q)}</p>)}
        </div>
      )}
      {approach.cover_letter && <DraftBox title="Cover letter" text={approach.cover_letter} copyText={approach.cover_letter} />}
      {!!approach.sources?.length && (
        <div className="space-y-1">
          <Subheading>Sources</Subheading>
          {approach.sources.map((source) => {
            const url = webUrl(source)
            return url ? (
              <a key={source} href={url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 truncate text-[11px] text-w-dim hover:text-w-text">
                <Link2 size={11} className="shrink-0" /> {hostOf(url)}
              </a>
            ) : null
          })}
        </div>
      )}
    </div>
  )
}

function Section({ title, trailing, children }: { title: string; trailing?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">{title}</h3>
        <div className="ml-auto">{trailing}</div>
      </div>
      {children}
    </section>
  )
}

function Subheading({ children }: { children: ReactNode }) {
  return <p className="pt-1 text-[11px] font-semibold text-w-text">{children}</p>
}

function Bullets({ title, items, numbered = false }: { title: string; items?: string[]; numbered?: boolean }) {
  if (!items?.length) return null
  return (
    <div className="space-y-1">
      <Subheading>{title}</Subheading>
      {items.map((item, i) => (
        <p key={`${i}-${item.slice(0, 24)}`} className="flex items-start gap-1.5 text-xs leading-5 text-w-text">
          <span className="w-4 shrink-0 text-right text-[11px] text-w-dim">{numbered ? `${i + 1}.` : '•'}</span>
          <span className="select-text">{item}</span>
        </p>
      ))}
    </div>
  )
}

function DraftBox({ title, header = '', text, copyText }: { title: string; header?: string; text: string; copyText: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(copyText)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div className="space-y-1.5 rounded-lg bg-w-surface2/60 p-3">
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[11px] font-semibold text-w-text">{title}</p>
        <button type="button" onClick={() => void copy()} className="shrink-0 text-[11px] font-semibold text-w-accent hover:underline">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {header && <p className="select-text whitespace-pre-line text-[11px] text-w-dim">{header}</p>}
      <p className="select-text whitespace-pre-wrap text-xs leading-5 text-w-text">{text}</p>
    </div>
  )
}
