import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../../api/client'
import { LABEL } from '../../../components/ui/typography'
import type { NewsletterDesign } from './blocks/schema'

export type ViewportKey = 'mobile' | 'desktop' | 'wide'
type ThemeKey = 'dark' | 'light'

const VIEWPORT_WIDTHS: Record<ViewportKey, number> = { mobile: 360, desktop: 640, wide: 800 }

export function MobilePreview({ title, subject, preheader, html, designJson, defaultTheme, viewport, onViewportChange }: {
  title: string; subject: string; preheader: string; html: string
  designJson?: NewsletterDesign | null
  defaultTheme?: ThemeKey
  viewport: ViewportKey; onViewportChange: (v: ViewportKey) => void
}) {
  // Iframe runs the SAME render pipeline as outbound mail — POSTs the draft
  // to /admin/newsletter/preview and inlines whatever the backend produces.
  // That's the only way the preview can stay honest about block layout,
  // branded chrome, theme palette, poster fallback, and CAN-SPAM footer.
  const [theme, setTheme] = useState<ThemeKey>(defaultTheme ?? 'dark')
  const [previewHtml, setPreviewHtml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  // When switching a draft into design mode (or opening a design draft), snap
  // the preview theme to the design's own preset so it matches send output.
  useEffect(() => { if (defaultTheme) setTheme(defaultTheme) }, [defaultTheme])

  const designKey = designJson ? JSON.stringify(designJson) : ''
  useEffect(() => {
    let cancelled = false
    setPreviewLoading(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.post<{ html: string }>('/admin/newsletter/preview', {
          title, subject, preheader, content_html: html, design_json: designJson ?? null, theme,
        })
        if (!cancelled) setPreviewHtml(res.html || '')
      } catch {
        if (!cancelled) setPreviewHtml('<p style="padding:16px;color:#a00;">Preview failed to render.</p>')
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 500)
    return () => { cancelled = true; window.clearTimeout(t) }
  }, [title, subject, preheader, html, designKey, theme])

  // The server returns a COMPLETE email document (its own <body> carries the
  // recipient-side background), so it's used verbatim as the iframe srcDoc.
  const clientBg = theme === 'dark' ? '#0a0a0a' : '#f3f4f6'
  const loadingDoc = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:${clientBg};font-family:-apple-system,system-ui,sans-serif;}</style></head><body><p style="padding:24px;color:#777;text-align:center;">Loading preview…</p></body></html>`
  const previewDoc = previewHtml || loadingDoc

  const viewportPx = VIEWPORT_WIDTHS[viewport]

  return (
    <div className="lg:sticky lg:top-4 self-start">
      <div className="flex items-center justify-between mb-2">
        <p className={LABEL}>Inbox preview {previewLoading && <Loader2 className="inline-block animate-spin ml-1" size={10} />}</p>
      </div>
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {(['mobile', 'desktop', 'wide'] as ViewportKey[]).map((v) => (
          <button
            key={v}
            onClick={() => onViewportChange(v)}
            className={`text-[10px] px-2 py-1 rounded ${viewport === v ? 'bg-white/[0.06] text-zinc-100' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'}`}
          >
            {v === 'mobile' ? 'Mobile' : v === 'desktop' ? 'Desktop' : 'Wide'} <span className="text-zinc-500">({VIEWPORT_WIDTHS[v]})</span>
          </button>
        ))}
        <div className="w-px h-4 mx-1 bg-white/[0.08]" />
        {(['dark', 'light'] as ThemeKey[]).map((t) => (
          <button
            key={t}
            onClick={() => setTheme(t)}
            className={`text-[10px] px-2 py-1 rounded ${theme === t ? 'bg-white/[0.06] text-zinc-100' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'}`}
          >
            {t === 'dark' ? 'Dark' : 'Light'}
          </button>
        ))}
      </div>
      <div className="rounded-2xl border-2 border-white/[0.06] bg-zinc-900 p-2" style={{ maxWidth: viewportPx + 16 }}>
        <div className="rounded-lg bg-zinc-950 overflow-hidden">
          <div className="px-3 py-2 border-b border-white/[0.06]">
            <p className="text-[11px] text-zinc-500">Inbox</p>
            <p className="text-xs text-zinc-200 font-medium truncate">{subject || 'Subject…'}</p>
            {preheader && <p className="text-[10px] text-zinc-500 truncate">{preheader}</p>}
          </div>
          <iframe
            title="Newsletter preview"
            sandbox="allow-same-origin"
            srcDoc={previewDoc}
            className="block"
            style={{ width: viewportPx, height: 700, border: 0, background: clientBg }}
          />
        </div>
      </div>
    </div>
  )
}
