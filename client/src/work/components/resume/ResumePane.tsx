import { useState } from 'react'
import { ArrowLeft, ExternalLink, FileText, Loader2, Lock, RefreshCw, Trash2 } from 'lucide-react'
import { getMyResume } from '../../../api/profileResume'
import { resumeFileProblem, useMyResume } from '../../hooks/useMyResume'
import { apiErrorText } from '../../utils/apiErrorText'
import ResumeDrop from './ResumeDrop'

const MIN_TEXT = 50
const MAX_TEXT = 20_000

/**
 * The person's résumé, in Tasks: where it is kept and who reads it, the file
 * they gave, what Espresso read from it, and the text Espresso uses, editable
 * in place. Editing changes what job searches read; the original file stays
 * as uploaded. Replacing the file reads it again from scratch.
 */
export default function ResumePane({ onBack }: { onBack?: () => void }) {
  const { resume, loaded, error, upload, saveText, remove } = useMyResume()
  const [draft, setDraft] = useState<{ base: string; text: string } | null>(null)
  const [busy, setBusy] = useState<'upload' | 'save' | 'delete' | 'open' | null>(null)
  const [replacing, setReplacing] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  // An edit belongs to the text it started from: a new upload starts over.
  const editing = draft !== null && resume !== null && draft.base === resume.text ? draft.text : null
  const text = editing ?? resume?.text ?? ''
  const dirty = editing !== null && editing !== resume?.text

  async function run(kind: NonNullable<typeof busy>, work: () => Promise<unknown>, done?: string) {
    setBusy(kind); setProblem(null); setNote(null)
    try { await work(); if (done) setNote(done) }
    catch (e) { setProblem(apiErrorText(e, 'That didn’t work. Try again in a moment.')) }
    finally { setBusy(null) }
  }

  function take(file: File) {
    const bad = resumeFileProblem(file)
    if (bad) { setProblem(bad); return }
    void run('upload', async () => { await upload(file); setDraft(null); setReplacing(false) }, 'Saved. Espresso read it again.')
  }

  function save() {
    const trimmed = text.trim()
    if (trimmed.length < MIN_TEXT) { setProblem('A résumé needs at least a few lines.'); return }
    void run('save', async () => { await saveText(trimmed); setDraft(null) }, 'Saved. New job searches read this text.')
  }

  function erase() {
    if (!window.confirm('Delete your résumé? The file and the text are removed. Job searches can still run without one.')) return
    void run('delete', async () => { await remove(); setDraft(null) })
  }

  // The file's link lasts fifteen minutes: get a fresh one when it's opened.
  // The tab opens on the click (a popup blocker allows that), then gets the
  // link; `noopener` would make `window.open` return null, so it's cut here.
  function openOriginal() {
    const opened = window.open('about:blank', '_blank')
    if (opened) opened.opener = null
    void run('open', async () => {
      try {
        const fresh = await getMyResume()
        if (!fresh?.resume_url) throw new Error('missing')
        if (opened) opened.location.href = fresh.resume_url
        else setNote('Your browser blocked the new tab. Allow pop-ups for Espresso and try again.')
      } catch (e) {
        opened?.close()
        throw e
      }
    })
  }

  const parsed = resume?.parsed_data ?? {}
  const facts = [
    ['Title', parsed.current_title],
    ['Experience', typeof parsed.experience_years === 'number' ? `${parsed.experience_years} years` : null],
    ['Location', parsed.location],
    ['Education', parsed.education],
  ].filter((f): f is [string, string] => !!f[1])

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 p-5 text-w-text">
      {onBack && (
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs text-w-dim hover:text-w-text md:hidden">
          <ArrowLeft size={13} /> Tasks
        </button>
      )}
      <header className="space-y-1.5">
        <h2 className="text-lg font-semibold">Your résumé</h2>
        <p className="flex items-start gap-1.5 text-xs leading-5 text-w-dim">
          <Lock size={12} className="mt-1 shrink-0" />
          <span>
            Private to you. The file is stored encrypted and opens only through a link that lasts fifteen minutes.
            Espresso’s AI reads it only for job searches you run with it: to judge fit, draft outreach and cover
            letters, and suggest roles beyond your title. It is never posted, shared, or sent to web searches.
          </span>
        </p>
      </header>

      {!loaded ? (
        <div role="status" aria-label="Loading your résumé" className="flex justify-center py-10"><Loader2 className="animate-spin text-w-dim" /></div>
      ) : error ? (
        <p role="alert" className="text-sm text-amber-500">{error}</p>
      ) : !resume ? (
        <ResumeDrop busy={busy === 'upload'} onFile={take} label="Drop your résumé here, or choose a file" />
      ) : (
        <>
          <section className="flex flex-wrap items-center gap-3 rounded-xl border border-w-line p-3">
            <FileText size={18} className="shrink-0 text-w-accent" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{resume.filename}</p>
              <p className="text-[11px] text-w-dim">Updated {new Date(resume.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" onClick={openOriginal} disabled={!!busy}
                className="inline-flex items-center gap-1 rounded-md border border-w-line px-2.5 py-1 text-xs hover:bg-w-surface2 disabled:opacity-50">
                <ExternalLink size={12} /> Open original
              </button>
              <button type="button" onClick={() => setReplacing((v) => !v)} disabled={!!busy} aria-expanded={replacing}
                className="inline-flex items-center gap-1 rounded-md border border-w-line px-2.5 py-1 text-xs hover:bg-w-surface2 disabled:opacity-50">
                <RefreshCw size={12} /> Replace
              </button>
              <button type="button" onClick={erase} disabled={!!busy}
                className="inline-flex items-center gap-1 rounded-md border border-w-line px-2.5 py-1 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text disabled:opacity-50">
                <Trash2 size={12} /> Delete
              </button>
            </div>
            {replacing && <div className="w-full"><ResumeDrop compact busy={busy === 'upload'} onFile={take} label="Drop the new résumé here" /></div>}
          </section>

          {(facts.length > 0 || (parsed.skills ?? []).length > 0 || parsed.summary) && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">What Espresso read</h3>
              {facts.length > 0 && (
                <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                  {facts.map(([label, value]) => (
                    <div key={label} className="flex gap-2"><dt className="shrink-0 text-w-dim">{label}</dt><dd className="min-w-0">{value}</dd></div>
                  ))}
                </dl>
              )}
              {(parsed.skills ?? []).length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {(parsed.skills ?? []).slice(0, 30).map((skill) => (
                    <span key={skill} className="rounded-full bg-w-surface2 px-2 py-0.5 text-[11px] text-w-text">{skill}</span>
                  ))}
                </div>
              )}
              {parsed.summary && <p className="text-xs leading-5 text-w-dim">{parsed.summary}</p>}
            </section>
          )}

          <section className="space-y-2">
            <div className="flex items-baseline gap-2">
              <h3 className="flex-1 text-sm font-semibold">The text Espresso uses</h3>
              <span className="text-[10px] text-w-faint">{text.length.toLocaleString()} / {MAX_TEXT.toLocaleString()}</span>
            </div>
            <p className="text-[11px] text-w-dim">Fix anything it read wrong or add what’s missing. Your original file stays as uploaded.</p>
            <textarea
              value={text}
              maxLength={MAX_TEXT}
              rows={18}
              aria-label="The text Espresso uses"
              onChange={(e) => setDraft({ base: resume.text, text: e.target.value })}
              className="w-full resize-y rounded-lg border border-w-line bg-w-surface2/40 p-3 font-mono text-xs leading-5 text-w-text focus:border-w-accent focus:outline-none"
            />
            <div className="flex items-center gap-2">
              <button type="button" onClick={save} disabled={!dirty || !!busy}
                className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi disabled:opacity-40">
                {busy === 'save' ? 'Saving…' : 'Save changes'}
              </button>
              {dirty && (
                <button type="button" onClick={() => setDraft(null)} disabled={!!busy}
                  className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-dim hover:text-w-text">Discard</button>
              )}
            </div>
          </section>
        </>
      )}
      {problem && <p role="alert" className="text-xs text-amber-500">{problem}</p>}
      {note && <p role="status" className="text-xs text-w-accent">{note}</p>}
    </div>
  )
}
