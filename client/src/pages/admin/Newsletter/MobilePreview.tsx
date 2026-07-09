import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../../api/client'

type ThemeKey = 'dark' | 'light'
type DeviceKey = 'desktop' | 'mobile'

const DEVICE_WIDTHS: Record<DeviceKey, number> = { desktop: 640, mobile: 360 }
const DEVICE_HEIGHTS: Record<DeviceKey, number> = { desktop: 460, mobile: 640 }

export function MobilePreview({ title, subject, preheader, html, theme, accentColor }: {
  title: string; subject: string; preheader: string; html: string
  theme: ThemeKey; accentColor: string
}) {
  // Iframe runs the SAME render pipeline as outbound mail — POSTs the draft
  // to /admin/newsletter/preview and inlines whatever the backend produces.
  // That's the only way the preview can stay honest about video poster
  // fallback, branded chrome, theme palette, accent color, and CAN-SPAM
  // footer changes. theme/accentColor are the Design settings panel's
  // values — this component just renders what's chosen there, live.
  const [previewHtml, setPreviewHtml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setPreviewLoading(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.post<{ html: string }>('/admin/newsletter/preview', {
          title, subject, preheader, content_html: html, theme, accent_color: accentColor,
        })
        if (!cancelled) setPreviewHtml(res.html || '')
      } catch {
        if (!cancelled) setPreviewHtml('<p style="padding:16px;color:#a00;">Preview failed to render.</p>')
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 500)
    return () => { cancelled = true; window.clearTimeout(t) }
  }, [title, subject, preheader, html, theme, accentColor])

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

  function DeviceFrame({ device }: { device: DeviceKey }) {
    const w = DEVICE_WIDTHS[device]
    const h = DEVICE_HEIGHTS[device]
    return (
      <div>
        <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider mb-1.5">
          {device === 'desktop' ? 'Desktop' : 'Mobile'} <span className="text-slate-400 font-normal normal-case">({w}px)</span>
        </p>
        <div className="rounded-2xl border-2 border-slate-200 bg-white shadow-sm p-2 inline-block" style={{ maxWidth: w + 16 }}>
          <div className="rounded-lg overflow-hidden" style={{ background: clientBg }}>
            <div className="px-3 py-2 border-b border-slate-200" style={{ background: theme === 'dark' ? '#0a0a0a' : '#ffffff' }}>
              <p className={`text-[11px] ${theme === 'dark' ? 'text-zinc-500' : 'text-slate-400'}`}>Inbox</p>
              <p className={`text-xs font-medium truncate ${theme === 'dark' ? 'text-zinc-200' : 'text-slate-800'}`} style={{ maxWidth: w }}>{subject || 'Subject…'}</p>
              {preheader && <p className={`text-[10px] truncate ${theme === 'dark' ? 'text-zinc-500' : 'text-slate-400'}`} style={{ maxWidth: w }}>{preheader}</p>}
            </div>
            <iframe
              title={`Newsletter preview — ${device}`}
              sandbox="allow-same-origin"
              srcDoc={previewDoc}
              className="block"
              style={{ width: w, height: h, border: 0, background: clientBg }}
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="lg:sticky lg:top-4 self-start">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <p className="text-[10px] text-slate-400 uppercase tracking-wider">Inbox preview {previewLoading && <Loader2 className="inline-block animate-spin ml-1" size={10} />}</p>
        <p className="text-[10px] text-slate-400">
          <span className="inline-block w-2 h-2 rounded-full align-[-1px] mr-1" style={{ background: accentColor }} />
          {theme === 'dark' ? 'Dark' : 'Light'} theme — edit in Design settings
        </p>
      </div>
      {/* Desktop + mobile shown together — no switching back and forth while drafting. */}
      <div className="space-y-4">
        <DeviceFrame device="desktop" />
        <DeviceFrame device="mobile" />
      </div>
    </div>
  )
}
