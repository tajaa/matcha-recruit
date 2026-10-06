import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Check, Sparkles, Eye, X, Sun, Moon } from 'lucide-react'
import { cappeApi } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { isPremiumPlan } from '../utils/plan'
import type { CappeTemplateSummary } from '../types'

const API_BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/cappe`
// Live preview is rendered at this design width, then scaled to fit the card.
const DESIGN_W = 1200
const DESIGN_H = 820

/** Preview URL for one page of a template. `premium` shows the polish a paid
 *  plan keeps; a free account sees exactly what its clone will keep. */
function templatePreviewUrl(slug: string, page = 'home', premium = false): string {
  const params = new URLSearchParams({ page })
  if (premium) params.set('premium', '1')
  return `${API_BASE}/templates/${slug}/preview?${params.toString()}`
}

/** Scaled, non-interactive live preview of a template's rendered home page. */
function PreviewFrame({ slug, name, premium }: { slug: string; name: string; premium: boolean }) {
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
        src={templatePreviewUrl(slug, 'home', premium)}
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

/** Full-size, browsable preview of every page of one template. Links inside
 *  the rendered page stay inside the iframe (the server rewrites them to
 *  `?page=`), and the tabs jump straight to a page. */
function PreviewModal({
  template, premium, busy, disabled, onPick, onClose,
}: {
  template: CappeTemplateSummary
  premium: boolean
  busy: boolean
  disabled: boolean
  onPick: () => void
  onClose: () => void
}) {
  const [page, setPage] = useState(template.pages[0]?.slug ?? 'home')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${template.name} preview`}
      className="fixed inset-0 z-50 flex flex-col bg-black/85 p-3 sm:p-6"
      onClick={onClose}
    >
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold text-zinc-100">{template.name}</h2>
            <p className="truncate text-xs text-zinc-500">{template.description}</p>
          </div>
          <div role="tablist" aria-label="Pages" className="flex flex-wrap gap-1">
            {template.pages.map((p) => (
              <button
                key={p.slug}
                type="button"
                role="tab"
                aria-selected={p.slug === page}
                onClick={() => setPage(p.slug)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  p.slug === page ? 'bg-zinc-100 text-zinc-950' : 'text-zinc-300 hover:bg-zinc-800'
                }`}
              >
                {p.title}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onPick}
            disabled={disabled}
            className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Use this template
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preview"
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <iframe
          key={page}
          title={`${template.name} — ${page}`}
          src={templatePreviewUrl(template.slug, page, premium)}
          sandbox="allow-scripts"
          className="min-h-0 flex-1 border-0 bg-white"
        />
      </div>
    </div>
  )
}

interface Props {
  /** Discover category the person told us about (onboarding) — its templates
   *  sort first and carry a "For you" badge. The whole shelf stays visible:
   *  with one or two templates per category, pre-filtering would hide the
   *  breadth that makes the shelf worth browsing. */
  category?: string | null
  /** Template currently being turned into a site (shows its spinner). */
  busySlug: string | null
  /** Disables every card, e.g. while a blank site is being created instead. */
  disabled?: boolean
  onPick: (template: CappeTemplateSummary) => void
}

const ALL = 'all'

/** The template catalog as preview cards with category filter chips and a
 *  full-site preview. Shared by the Templates page and the onboarding wizard's
 *  "how do you want to start?" step. Every template is available on every
 *  plan; a paid account's previews show the premium polish it will keep. */
export default function TemplateGallery({ category, busySlug, disabled = false, onPick }: Props) {
  const { account } = useCappeMe()
  const premium = isPremiumPlan(account?.plan)
  const [templates, setTemplates] = useState<CappeTemplateSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<string>(ALL)
  const [previewing, setPreviewing] = useState<CappeTemplateSummary | null>(null)

  useEffect(() => {
    cappeApi
      .get<CappeTemplateSummary[]>('/templates')
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load templates'))
  }, [])

  const chips = useMemo(() => {
    if (!templates) return []
    const seen = new Map<string, string>()
    templates.forEach((t) => seen.set(t.category, t.category_label))
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [templates])

  // A chip for a category with no templates would filter to nothing; fall
  // back to the whole shelf but still sort that category's neighbours first.
  const activeFilter = chips.some(([slug]) => slug === filter) ? filter : ALL

  const ordered = useMemo(() => {
    if (!templates) return null
    const shown = activeFilter === ALL ? templates : templates.filter((t) => t.category === activeFilter)
    if (!category) return shown
    return [...shown].sort((a, b) => Number(b.category === category) - Number(a.category === category))
  }, [templates, activeFilter, category])

  if (error) return <p role="alert" className="text-sm text-red-400">{error}</p>
  if (ordered === null) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }
  if (templates && templates.length === 0) {
    return <p className="text-sm text-zinc-500">No templates are available right now.</p>
  }

  return (
    <div>
      <div role="group" aria-label="Filter by category" className="mb-5 flex flex-wrap gap-1.5">
        {[[ALL, 'All'] as [string, string], ...chips].map(([slug, label]) => {
          const active = slug === activeFilter
          return (
            <button
              key={slug}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(slug)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                active
                  ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300'
                  : 'border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {ordered.length === 0 ? (
        <p className="text-sm text-zinc-500">No templates in this category yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {ordered.map((t) => {
            const recommended = !!category && t.category === category
            const busy = busySlug === t.slug
            return (
              <div key={t.slug} className="group flex flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900 transition hover:border-zinc-700">
                <PreviewFrame slug={t.slug} name={t.name} premium={premium} />
                <div className="flex flex-1 flex-col p-5">
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <h3 className="font-medium text-zinc-100">{t.name}</h3>
                    <span className="flex shrink-0 items-center gap-2">
                      {recommended && (
                        <span className="flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
                          <Sparkles className="h-3 w-3" />
                          For you
                        </span>
                      )}
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium uppercase text-zinc-400">
                        {t.category_label}
                      </span>
                    </span>
                  </div>
                  <p className="mb-2 flex items-center gap-1.5 text-[11px] text-zinc-500">
                    {t.mode === 'dark' ? <Moon className="h-3 w-3" /> : <Sun className="h-3 w-3" />}
                    {t.mode === 'dark' ? 'Dark' : 'Light'} · {t.heading_font} · {t.pages.length} page{t.pages.length === 1 ? '' : 's'}
                  </p>
                  <p className="mb-4 flex-1 text-sm text-zinc-400">{t.description}</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setPreviewing(t)}
                      disabled={disabled}
                      aria-label={`Preview the ${t.name} template`}
                      className="flex items-center justify-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
                    >
                      <Eye className="h-4 w-4" />
                      Preview
                    </button>
                    <button
                      type="button"
                      onClick={() => onPick(t)}
                      disabled={disabled || busySlug !== null}
                      aria-label={`Use the ${t.name} template`}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
                    >
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      Use this template
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {previewing && (
        <PreviewModal
          template={previewing}
          premium={premium}
          busy={busySlug === previewing.slug}
          disabled={disabled || busySlug !== null}
          onPick={() => onPick(previewing)}
          onClose={() => setPreviewing(null)}
        />
      )}
    </div>
  )
}
