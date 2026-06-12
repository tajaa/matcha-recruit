import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Check, Sparkles } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import { useCappeMe } from '../../hooks/useCappeMe'
import type { CappeSite, CappeTemplateSummary } from '../../types/cappe'

// Which template categories fit each account type best — recommended ones
// sort first and get a badge. Same catalog for everyone; just emphasis.
const RECOMMENDED_CATEGORIES: Record<string, Set<string>> = {
  business: new Set(['business', 'food']),
  personal: new Set(['portfolio', 'blog']),
}

const API_BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/cappe`
// Live preview is rendered at this design width, then scaled to fit the card.
const DESIGN_W = 1200
const DESIGN_H = 820

/** Scaled, non-interactive live preview of a template's rendered home page. */
function PreviewFrame({ slug, name }: { slug: string; name: string }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.25)
  const [loaded, setLoaded] = useState(false)

  useLayoutEffect(() => {
    const el = boxRef.current
    if (!el) return
    const measure = () => setScale(el.clientWidth / DESIGN_W)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div
      ref={boxRef}
      className="relative w-full overflow-hidden border-b border-zinc-800 bg-zinc-950"
      style={{ height: DESIGN_H * scale }}
    >
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
        </div>
      )}
      <iframe
        title={`${name} preview`}
        src={`${API_BASE}/templates/${slug}/preview`}
        sandbox="allow-scripts"
        loading="lazy"
        onLoad={() => setLoaded(true)}
        tabIndex={-1}
        className="pointer-events-none origin-top-left border-0"
        style={{
          width: DESIGN_W,
          height: DESIGN_H,
          transform: `scale(${scale})`,
          opacity: loaded ? 1 : 0,
          transition: 'opacity .3s',
        }}
      />
    </div>
  )
}

export default function CappeTemplates() {
  const navigate = useNavigate()
  const { account } = useCappeMe()
  const [templates, setTemplates] = useState<CappeTemplateSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [usingId, setUsingId] = useState<string | null>(null)

  useEffect(() => {
    cappeApi
      .get<CappeTemplateSummary[]>('/templates')
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load templates'))
  }, [])

  const recommended = RECOMMENDED_CATEGORIES[account?.account_type ?? ''] ?? null
  const ordered = useMemo(() => {
    if (!templates) return null
    if (!recommended) return templates
    return [...templates].sort(
      (a, b) => Number(recommended.has(b.category)) - Number(recommended.has(a.category))
    )
  }, [templates, recommended])

  async function useTemplate(t: CappeTemplateSummary) {
    setUsingId(t.id)
    setError(null)
    try {
      const site = await cappeApi.post<CappeSite>('/sites/from-template', {
        template_id: t.id,
        name: t.name,
      })
      navigate(`/cappe/sites/${site.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create site')
      setUsingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Templates</h1>
        <p className="mt-1 text-sm text-zinc-400">Pick a design — we'll clone it into a new site you can edit.</p>
      </div>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {ordered === null ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {ordered.map((t) => (
            <div key={t.id} className="group flex flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900 transition hover:border-zinc-700">
              <PreviewFrame slug={t.slug} name={t.name} />
              <div className="flex flex-1 flex-col p-5">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="font-medium text-zinc-100">{t.name}</h3>
                  <span className="flex items-center gap-2">
                    {recommended?.has(t.category) && (
                      <span className="flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
                        <Sparkles className="h-3 w-3" />
                        For you
                      </span>
                    )}
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium uppercase text-zinc-400">
                      {t.category}
                    </span>
                  </span>
                </div>
                <p className="mb-4 flex-1 text-sm text-zinc-400">{t.description}</p>
                <button
                  onClick={() => useTemplate(t)}
                  disabled={usingId !== null}
                  className="flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
                >
                  {usingId === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Use this template
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
