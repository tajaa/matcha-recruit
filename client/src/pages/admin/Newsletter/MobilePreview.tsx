import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../../api/client'

export type ViewportKey = 'mobile' | 'desktop' | 'wide'
type ThemeKey = 'dark' | 'light'

const VIEWPORT_WIDTHS: Record<ViewportKey, number> = { mobile: 360, desktop: 640, wide: 800 }

export function MobilePreview({ title, subject, preheader, html, viewport, onViewportChange }: {
  title: string; subject: string; preheader: string; html: string
  viewport: ViewportKey; onViewportChange: (v: ViewportKey) => void
}) {
  // Iframe runs the SAME render pipeline as outbound mail — POSTs the draft
  // to /admin/newsletter/preview and inlines whatever the backend produces.
  // That's the only way the preview can stay honest about video poster
  // fallback, branded chrome, theme palette, and CAN-SPAM footer changes.
  const [theme, setTheme] = useState<ThemeKey>('light')
  const [previewHtml, setPreviewHtml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setPreviewLoading(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.post<{ html: string }>('/admin/newsletter/preview', {
          title, subject, preheader, content_html: html, theme,
        })
        if (!cancelled) setPreviewHtml(res.html || '')
      } catch {
        if (!cancelled) setPreviewHtml('<p style="padding:16px;color:#a00;">Preview failed to render.</p>')
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 500)
    return () => { cancelled = true; window.clearTimeout(t) }
  }, [title, subject, preheader, html, theme])

  // Wrap server-rendered fragment in a minimal HTML document. The server
  // returns the email body div; we add a doctype + the recipient-side
  // background that simulates what the email client paints around the email.
  const clientBg = theme === 'dark' ? '#0a0a0a' : '#f3f4f6'
  const previewDoc = `<!doctype html><html><head><meta charset="utf-8"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"><style>
    html,body{margin:0;padding:0;background:${clientBg};}
    body{padding:16px 0;font-family:'Inter',-apple-system,system-ui,sans-serif;}
    img{max-width:100%;height:auto}
    video{max-width:100%;height:auto}
  </style></head><body>${previewHtml || '<p style="padding:16px;color:#777;text-align:center;">Loading preview…</p>'}</body></html>`

  const viewportPx = VIEWPORT_WIDTHS[viewport]

  return (
    <div className="lg:sticky lg:top-4 self-start">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-slate-400 uppercase tracking-wider">Inbox preview {previewLoading && <Loader2 className="inline-block animate-spin ml-1" size={10} />}</p>
      </div>
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {(['mobile', 'desktop', 'wide'] as ViewportKey[]).map((v) => (
          <button
            key={v}
            onClick={() => onViewportChange(v)}
            className={`text-[10px] px-2 py-1 rounded ${viewport === v ? 'bg-slate-800 text-white' : 'bg-white border border-slate-200 text-slate-500 hover:text-slate-800'}`}
          >
            {v === 'mobile' ? 'Mobile' : v === 'desktop' ? 'Desktop' : 'Wide'} <span className={viewport === v ? 'text-slate-300' : 'text-slate-400'}>({VIEWPORT_WIDTHS[v]})</span>
          </button>
        ))}
        <div className="w-px h-4 mx-1 bg-slate-200" />
        {(['dark', 'light'] as ThemeKey[]).map((t) => (
          <button
            key={t}
            onClick={() => setTheme(t)}
            title="Preview how the sent email renders in the recipient's mail client theme"
            className={`text-[10px] px-2 py-1 rounded ${theme === t ? 'bg-slate-800 text-white' : 'bg-white border border-slate-200 text-slate-500 hover:text-slate-800'}`}
          >
            {t === 'dark' ? 'Dark' : 'Light'}
          </button>
        ))}
      </div>
      <div className="rounded-2xl border-2 border-slate-200 bg-white shadow-sm p-2" style={{ maxWidth: viewportPx + 16 }}>
        <div className="rounded-lg overflow-hidden" style={{ background: clientBg }}>
          <div className="px-3 py-2 border-b border-slate-200" style={{ background: theme === 'dark' ? '#0a0a0a' : '#ffffff' }}>
            <p className={`text-[11px] ${theme === 'dark' ? 'text-zinc-500' : 'text-slate-400'}`}>Inbox</p>
            <p className={`text-xs font-medium truncate ${theme === 'dark' ? 'text-zinc-200' : 'text-slate-800'}`}>{subject || 'Subject…'}</p>
            {preheader && <p className={`text-[10px] truncate ${theme === 'dark' ? 'text-zinc-500' : 'text-slate-400'}`}>{preheader}</p>}
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
