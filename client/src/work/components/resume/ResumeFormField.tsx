import { useState } from 'react'
import { Link, useInRouterContext } from 'react-router-dom'
import { CheckCircle2, FileText, Lock } from 'lucide-react'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { resumeFileProblem, useMyResume } from '../../hooks/useMyResume'
import { apiErrorText } from '../../utils/apiErrorText'
import ResumeDrop from './ResumeDrop'
import { resumePath } from './paths'

/**
 * Under a job search form's "Use my résumé" switch: the saved résumé (and
 * where to read and edit it), or, when there is none and the switch is on, a
 * place to drop one in. It is saved to the person's profile, privately, the
 * moment it is dropped, and shows in Tasks → Résumé.
 */
export default function ResumeFormField({ on }: { on: boolean }) {
  const base = useWorkBase()
  const { resume, loaded, upload } = useMyResume()
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)
  const routed = useInRouterContext()

  async function take(file: File) {
    const bad = resumeFileProblem(file)
    if (bad) { setProblem(bad); return }
    setBusy(true); setProblem(null)
    try { await upload(file); setJustSaved(true) }
    catch (e) { setProblem(apiErrorText(e, "Couldn't read that résumé. Try a PDF or Word file.")) }
    finally { setBusy(false) }
  }

  if (!loaded) return null
  const where = routed
    ? <Link to={resumePath(base)} className="font-medium text-w-accent hover:underline">View or edit</Link>
    : <a href={resumePath(base)} className="font-medium text-w-accent hover:underline">View or edit</a>
  if (resume) {
    return (
      <div className="space-y-0.5 rounded-lg bg-w-surface2/60 px-2.5 py-2 text-[11px] text-w-dim">
        <p className="flex items-center gap-1.5 text-w-text">
          {justSaved ? <CheckCircle2 size={12} className="text-w-accent" /> : <FileText size={12} />}
          <span className="truncate font-medium">{resume.filename}</span>
          <span className="shrink-0">{justSaved ? 'saved' : on ? 'will be used' : 'not used'}</span>
        </p>
        <p className="flex items-center gap-1"><Lock size={10} /> Private to you. {where}</p>
      </div>
    )
  }
  if (!on) return null
  return (
    <div className="space-y-1">
      <ResumeDrop compact busy={busy} onFile={(file) => void take(file)} label="Drop your résumé here to use it" />
      <p className="flex items-center gap-1 text-[10px] text-w-dim">
        <Lock size={10} /> Kept private and encrypted, for your searches only.
      </p>
      {problem && <p role="alert" className="text-[11px] text-amber-500">{problem}</p>}
    </div>
  )
}
