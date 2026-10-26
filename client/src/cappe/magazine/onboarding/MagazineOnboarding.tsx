import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check, Loader2, LockKeyhole, X } from 'lucide-react'
import { CappeApiError, cappeApi } from '../../api'
import { ui } from '../../components/ui'
import { CAPPE_HOST } from '../../host'
import type { CappeHandleCheck, CappeMagazineOptions, CappeMagazineStartResult, MastheadStyle } from '../../types'
import type { Doc } from '../../studio/model/types'
import { handleFrom } from '../writers/handles'
import MagazineDesigns from './MagazineDesigns'

const MAX_TOPICS = 3
type StartRequest = {
  name: string; handle: string; tagline: string | null; topics: string[]; masthead_style: MastheadStyle
  request_id: string; doc: Doc
}

/** Name, art direction, then a private ten-page draft in Studio. */
export default function MagazineOnboarding() {
  const navigate = useNavigate()
  const [options, setOptions] = useState<CappeMagazineOptions | null>(null)
  const [name, setName] = useState('')
  const [handle, setHandle] = useState('')
  const [handleEdited, setHandleEdited] = useState(false)
  const [check, setCheck] = useState<CappeHandleCheck | null>(null)
  const [tagline, setTagline] = useState('')
  const [topics, setTopics] = useState<string[]>([])
  const [masthead, setMasthead] = useState<MastheadStyle>('classic')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState('quiet-form')
  const [doc, setDoc] = useState<Doc | null>(null)
  const [pending, setPending] = useState<StartRequest | null>(null)
  const requestId = useRef(crypto.randomUUID())
  const submitting = useRef(false)

  useEffect(() => {
    cappeApi.get<CappeMagazineOptions>('/magazine/options').then(setOptions)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the options'))
  }, [])

  const address = handleEdited ? handle : handleFrom(name)

  // The address is checked a moment after typing settles.
  useEffect(() => {
    if (address.length < 3) return
    let live = true
    const t = setTimeout(() => {
      cappeApi.get<CappeHandleCheck>(`/magazine/handle-available?handle=${encodeURIComponent(address)}`)
        .then((c) => { if (live) setCheck(c) }).catch(() => {})
    }, 400)
    return () => { live = false; clearTimeout(t) }
  }, [address])

  const current = check && check.handle === address ? check : null
  const toggleTopic = (key: string) => setTopics((t) => (t.includes(key) ? t.filter((k) => k !== key)
    : t.length >= MAX_TOPICS ? t : [...t, key]))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (submitting.current) return
    let body = pending
    if (!body) {
      if (!doc || !name.trim() || address.length < 3 || (current !== null && !current.available)) return
      body = { name: name.trim(), handle: address, tagline: tagline.trim() || null, topics, masthead_style: masthead,
        request_id: requestId.current, doc }
    }
    submitting.current = true
    setPending(body)
    setBusy(true)
    setError(null)
    try {
      const result = await cappeApi.post<CappeMagazineStartResult>('/magazine/quick-start', body)
      navigate(`/cappe/studio/${result.site.id}/story/${result.post_id}`, { replace: true })
    } catch (err) {
      // An initial client rejection did not create a draft. After an uncertain
      // outcome, even a later rejection cannot rule out that earlier commit.
      if (!pending && err instanceof CappeApiError && err.status && err.status >= 400 && err.status < 500) setPending(null)
      setError(err instanceof Error ? err.message : 'Your magazine could not be created')
    } finally {
      setBusy(false)
      submitting.current = false
    }
  }

  if (!options && !error) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:p-8">
      <p className="mb-3 text-xs uppercase tracking-[0.24em] text-emerald-400">Gummfit Magazines</p>
      <h1 className="text-3xl font-medium tracking-tight text-zinc-50 sm:text-4xl">Your magazine starts here.</h1>
      <p className={`${ui.subtitle} mb-8 mt-3 max-w-xl leading-relaxed`}>Give it a name. Find its look. Open a complete draft and make it yours.</p>
      <form onSubmit={submit} className="space-y-8" aria-label="Your magazine">
        <fieldset disabled={busy || !!pending} className="space-y-8">
          <section className={`${ui.card} space-y-5 p-5 sm:p-6`} aria-label="Magazine details">
            <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">01 / Your publication</p>
            <label className="block">
              <span className={ui.label}>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} className={ui.input}
                placeholder="The Harbour Review" />
            </label>
            <label className="block">
              <span className={ui.label}>Address</span>
              <div className="flex items-center gap-2">
                <input value={address} maxLength={30} className={ui.input} aria-describedby="handle-status"
                  onChange={(e) => { setHandleEdited(true); setHandle(e.target.value.toLowerCase()) }} />
                <span className="shrink-0 text-sm text-zinc-500">.{CAPPE_HOST}</span>
              </div>
              <span id="handle-status" className="mt-1 flex items-center gap-1 text-xs" aria-live="polite">
                {address.length >= 3 && current && (current.available
                  ? <><Check className="h-3.5 w-3.5 text-emerald-400" /><span className="text-emerald-400">{address}.{CAPPE_HOST} is yours to take</span></>
                  : <><X className="h-3.5 w-3.5 text-red-400" /><span className="text-red-400">{current.reason}</span></>)}
              </span>
            </label>
            <details className="space-y-5">
              <summary className="cursor-pointer text-sm text-zinc-400">Optional details · tagline, topics and website masthead</summary>
              <label className="block">
                <span className={ui.label}>Tagline</span>
                <input value={tagline} onChange={(e) => setTagline(e.target.value)} maxLength={200} className={ui.input}
                  placeholder="Stories from the water" />
              </label>
              <fieldset>
                <legend className={ui.label}>Topics (up to {MAX_TOPICS})</legend>
                <div className="flex flex-wrap gap-2">
                  {options?.topics.map((t) => (
                    <button key={t.key} type="button" aria-pressed={topics.includes(t.key)} onClick={() => toggleTopic(t.key)}
                      className={`rounded-full border px-3 py-1 text-sm ${topics.includes(t.key) ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 text-zinc-300 hover:border-zinc-500'}`}>
                      {t.label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend className={ui.label}>Masthead</legend>
                <div className="grid gap-2 sm:grid-cols-3">
                  {options?.mastheads.map((m) => (
                    <button key={m.key} type="button" aria-pressed={masthead === m.key} onClick={() => setMasthead(m.key)}
                      className={`rounded-xl border p-3 text-left ${masthead === m.key ? 'border-emerald-500 bg-emerald-500/10' : 'border-zinc-700 hover:border-zinc-500'}`}>
                      <span className="block text-lg text-zinc-100" style={{ fontFamily: `'${m.heading}', serif` }}>{name || 'Your magazine'}</span>
                      <span className="block text-xs text-zinc-500">{m.heading} · {m.body}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
            </details>
          </section>
          <MagazineDesigns name={name} selected={selected} onSelect={setSelected} onReady={setDoc} disabled={busy || !!pending} />
        </fieldset>
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        {pending && !busy && <p className="text-sm text-zinc-400">Your setup details are kept while we confirm the result. Retry opening your draft.</p>}
        <div className="flex flex-col gap-4 border-t border-zinc-800 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-start gap-2 text-xs leading-relaxed text-zinc-400"><LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" /><span>Private until you publish.<br />No plan purchase needed to start.</span></p>
          <button type="submit" className={ui.btnPrimary}
            disabled={busy || (!pending && (!doc || !name.trim() || address.length < 3 || (current !== null && !current.available)))}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} {busy ? 'Creating your draft…' : pending ? 'Retry opening my draft' : 'Open my first draft'}
          </button>
        </div>
      </form>
    </div>
  )
}
