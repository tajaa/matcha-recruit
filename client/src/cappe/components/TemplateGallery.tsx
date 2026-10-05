import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Check, Sparkles } from 'lucide-react'
import { cappeApi } from '../api'
import type { CappeTemplateSummary } from '../types'

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

interface Props {
  accountType?: string
  /** Template currently being turned into a site (shows its spinner). */
  busyId: string | null
  /** Disables every card, e.g. while a blank site is being created instead. */
  disabled?: boolean
  onPick: (template: CappeTemplateSummary) => void
}

/** The template catalog as preview cards. Shared by the Templates page and the
 *  onboarding wizard's "how do you want to start?" step. */
export default function TemplateGallery({ accountType, busyId, disabled = false, onPick }: Props) {
  const [templates, setTemplates] = useState<CappeTemplateSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi
      .get<CappeTemplateSummary[]>('/templates')
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load templates'))
  }, [])

  const recommended = RECOMMENDED_CATEGORIES[accountType ?? ''] ?? null
  const ordered = useMemo(() => {
    if (!templates) return null
    if (!recommended) return templates
    return [...templates].sort(
      (a, b) => Number(recommended.has(b.category)) - Number(recommended.has(a.category))
    )
  }, [templates, recommended])

  if (error) return <p role="alert" className="text-sm text-red-400">{error}</p>
  if (ordered === null) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }
  if (ordered.length === 0) return <p className="text-sm text-zinc-500">No templates are available right now.</p>

  return (
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
              type="button"
              onClick={() => onPick(t)}
              disabled={disabled || busyId !== null}
              aria-label={`Use the ${t.name} template`}
              className="flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
            >
              {busyId === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              Use this template
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
