// Export: download a print PNG, or push one to the campaign as its flyer image
// (which is what the public claim page renders).
import { useState } from 'react'
import { Download, ImageUp } from 'lucide-react'
import type Konva from 'konva'
import type { FlyerDesign } from '../../api/types'
import { promoApi } from '../../api/promo'
import { Button, ErrorText } from '../ui'

// Artboards are authored at 150dpi print pixels, so a 150dpi export is the
// artboard 1:1 and 300dpi is 2x. The Stage itself is scaled down to fit the
// screen, so that screen scale has to be divided back out or the export would
// come out at preview resolution.
export async function exportPng(
  stage: Konva.Stage,
  ensureReady: () => Promise<void>,
  dpi: 150 | 300,
): Promise<Blob> {
  // Fonts AND the QR rasters — an unresolved font bakes fallback metrics into
  // the layout, and an unresolved QR bakes the placeholder in where the only
  // scannable element belongs.
  await ensureReady()
  const overlay = stage.findOne<Konva.Layer>('.designer-overlay')
  const wasVisible = overlay?.visible() ?? false
  overlay?.visible(false)
  try {
    const pixelRatio = (dpi / 150) / (stage.scaleX() || 1)
    // toDataURL throws SecurityError if any image tainted the canvas — see the
    // crossOrigin note in LayerRenderer.
    const dataUrl = stage.toDataURL({ pixelRatio, mimeType: 'image/png' })
    const res = await fetch(dataUrl)
    return await res.blob()
  } finally {
    overlay?.visible(wasVisible)
    overlay?.getLayer()?.batchDraw()
  }
}

export function ExportMenu({
  stageRef, campaignId, design, ensureReady, onFlyerSaved,
}: {
  stageRef: React.RefObject<Konva.Stage | null>
  campaignId: string
  design: FlyerDesign
  /** Awaits everything the capture depends on: fonts + QR rasters. */
  ensureReady: () => Promise<void>
  onFlyerSaved: (url: string) => void
}) {
  const [busy, setBusy] = useState<'' | 'png150' | 'png300' | 'flyer'>('')
  const [err, setErr] = useState('')

  async function run(kind: 'png150' | 'png300' | 'flyer') {
    const stage = stageRef.current
    if (!stage) return
    setBusy(kind); setErr('')
    try {
      const blob = await exportPng(stage, ensureReady, kind === 'png300' ? 300 : 150)
      if (kind === 'flyer') {
        const form = new FormData()
        form.append('file', blob, 'flyer.png')
        const { flyer_image_url } = await promoApi.uploadFlyer(campaignId, form)
        onFlyerSaved(flyer_image_url)
        return
      }
      // The anchor must be attached to the document before .click() — an
      // untethered anchor's click doesn't reliably register as a real download
      // gesture in Chrome, which then shows a phantom "Unconfirmed" entry and
      // can save a second, truncated copy instead of the real file. Same
      // reason the object URL is revoked on a later task, not this one: the
      // browser may not have started reading the blob yet. (See the identical
      // note on _saveBlobResponse in the matcha client's api/client.ts.)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `flyer-${design.artboard.preset}-${kind === 'png300' ? '300dpi' : '150dpi'}.png`
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch (e) {
      // The realistic failure is a tainted canvas from a cross-origin logo the
      // bucket won't CORS — say so rather than leaking "SecurityError".
      const msg = e instanceof Error ? e.message : 'Export failed'
      setErr(/security|tainted/i.test(msg) ? 'Export blocked: an image on the canvas is not CORS-readable.' : msg)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="soft" loading={busy === 'png150'} onClick={() => void run('png150')}>
          <Download className="h-3.5 w-3.5" /> PNG 150dpi
        </Button>
        <Button size="sm" variant="soft" loading={busy === 'png300'} onClick={() => void run('png300')}>
          <Download className="h-3.5 w-3.5" /> PNG 300dpi
        </Button>
        <Button size="sm" loading={busy === 'flyer'} onClick={() => void run('flyer')}>
          <ImageUp className="h-3.5 w-3.5" /> Use as campaign flyer
        </Button>
      </div>
      <ErrorText>{err}</ErrorText>
    </div>
  )
}
