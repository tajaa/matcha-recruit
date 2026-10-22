import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Loader2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import { CAPPE_HOST } from '../../host'
import type { CappeHandleCheck, CappeMagazineOptions, CappeSite, MastheadStyle } from '../../types'
import { handleFrom } from '../writers/handles'
import { storiesPath } from '../writers/writerPaths'

const MAX_TOPICS = 3

/** `/cappe/writer/new` — name the magazine, choose its address, topics and
 *  masthead. The address is exactly the handle chosen. */
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
    setBusy(true)
    setError(null)
    try {
      const site = await cappeApi.post<CappeSite>('/magazine/sites', {
        name: name.trim(), handle: address, tagline: tagline.trim() || null, topics, masthead_style: masthead,
      })
      navigate(storiesPath(site.id), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Your magazine could not be created')
    } finally {
      setBusy(false)
    }
  }

  if (!options && !error) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className={ui.heading}>Name your magazine</h1>
      <p className={`${ui.subtitle} mb-6`}>You can change all of this later, except the address.</p>
      <form onSubmit={submit} className={`${ui.card} space-y-5 p-6`} aria-label="Your magazine">
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
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        <div className="flex items-center gap-3">
          <button type="submit" className={ui.btnPrimary}
            disabled={busy || !name.trim() || address.length < 3 || (current !== null && !current.available)}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create my magazine
          </button>
        </div>
      </form>
    </div>
  )
}
