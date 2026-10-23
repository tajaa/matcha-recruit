import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { CircleHelp, FlipHorizontal2, FlipVertical2, Loader2, Redo2, RotateCcw, RotateCw, Undo2, X } from 'lucide-react'
import type { CappeAsset } from '../../types'
import { studioApi } from '../api'
import type { Asset } from '../model/types'
import { outputUv, sourceUv } from './develop'
import { PictureGL } from './gl'
import { LOOKS, withLook } from './looks'
import {
  ANGLE_MAX, CROP_MIN, FEATHER_MAX, MAX_POINTS, WHOLE, normalizeRecipe, outputSize, turned,
  type Crop, type CutPoint, type Recipe, type Slider,
} from './recipe'
import { WorkerSegmenter, type Mask, type Segmenter } from './segment'

type Mode = 'adjust' | 'crop' | 'cutout'
type Source = { bitmap: ImageBitmap; w: number; h: number; png: boolean; id: string }
type Seg = { state: 'off' | 'loading' | 'encoding' | 'ready' | 'error'; done: number; total: number; message: string | null }

const PREVIEW_MAX = 2048
const THUMB = 112
const MASKS_KEPT = 6
const ASPECTS: { key: string; label: string; ratio: number | null }[] = [
  { key: 'free', label: 'Free', ratio: null }, { key: 'original', label: 'Original', ratio: 0 },
  { key: '1:1', label: '1:1', ratio: 1 }, { key: '4:5', label: '4:5', ratio: 4 / 5 }, { key: '3:4', label: '3:4', ratio: 3 / 4 },
  { key: '2:3', label: '2:3', ratio: 2 / 3 }, { key: '16:9', label: '16:9', ratio: 16 / 9 },
]
const GROUPS: { title: string; sliders: { key: Slider; label: string; min: number; max: number; step?: number; hue?: boolean }[] }[] = [
  { title: 'Light', sliders: [
    { key: 'exposure', label: 'Exposure', min: -4, max: 4, step: 0.01 }, { key: 'contrast', label: 'Contrast', min: -100, max: 100 },
    { key: 'highlights', label: 'Highlights', min: -100, max: 100 }, { key: 'shadows', label: 'Shadows', min: -100, max: 100 },
    { key: 'whites', label: 'Whites', min: -100, max: 100 }, { key: 'blacks', label: 'Blacks', min: -100, max: 100 },
  ] },
  { title: 'Colour', sliders: [
    { key: 'temp', label: 'Temperature', min: -100, max: 100 }, { key: 'tint', label: 'Tint', min: -100, max: 100 },
    { key: 'vibrance', label: 'Vibrance', min: -100, max: 100 }, { key: 'saturation', label: 'Saturation', min: -100, max: 100 },
  ] },
  { title: 'Effects', sliders: [
    { key: 'clarity', label: 'Clarity', min: -100, max: 100 }, { key: 'sharpen', label: 'Sharpen', min: 0, max: 100 },
    { key: 'vignette', label: 'Vignette', min: -100, max: 100 }, { key: 'grain', label: 'Grain', min: 0, max: 100 },
    { key: 'fade', label: 'Fade', min: 0, max: 100 },
  ] },
  { title: 'Split toning', sliders: [
    { key: 'sh_hue', label: 'Shadows hue', min: 0, max: 360, hue: true }, { key: 'sh_amt', label: 'Shadows', min: 0, max: 100 },
    { key: 'hi_hue', label: 'Highlights hue', min: 0, max: 360, hue: true }, { key: 'hi_amt', label: 'Highlights', min: 0, max: 100 },
  ] },
]

const fit = (w: number, h: number, box: { w: number; h: number }) => {
  const k = Math.min(box.w / w, box.h / h)
  return { w: Math.max(1, Math.floor(w * k)), h: Math.max(1, Math.floor(h * k)) }
}
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback)

/** Gummfit Studio's Picture Editor: looks, light and colour, crop and
 *  straighten, and cutting a subject out of its background, drawn live with
 *  WebGL (gl.ts). Nothing changes the library picture: Done draws the edit at
 *  full size and saves it as a new picture made from this one (the server
 *  keeps the recipe, the source and its credit). Editing an edited picture
 *  starts again from its source, with its recipe. */
export default function PictureEditor({ siteId, asset, startIn = 'adjust', onDone, onClose, onHelp }: {
  siteId: string
  asset: Asset
  startIn?: Mode
  onDone: (saved: CappeAsset) => void
  onClose: () => void
  /** Open the Studio's guide at this section (`picture` or `cutout`). */
  onHelp?: (section: 'picture' | 'cutout') => void
}) {
  const reopened = asset.kind === 'edit' && !!asset.parent
  const [recipe, setRecipe] = useState<Recipe>(() => (reopened ? normalizeRecipe(asset.recipe) : {}))
  const [past, setPast] = useState<Recipe[]>([])
  const [future, setFuture] = useState<Recipe[]>([])
  const [mode, setMode] = useState<Mode>(startIn)
  const [src, setSrc] = useState<Source | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [before, setBefore] = useState(false)
  const [thumbs, setThumbs] = useState<Record<string, string>>({})
  const [box, setBox] = useState({ w: 800, h: 600 })
  const [aspect, setAspect] = useState('free')
  const [seg, setSeg] = useState<Seg>({ state: 'off', done: 0, total: 0, message: null })
  // Masks by the clicks they were made from (the last few: undo and redo
  // come back to them), and the last click the model couldn't cut out.
  const [masks, setMasks] = useState<Map<string, Mask>>(() => new Map())
  const [maskError, setMaskError] = useState<{ key: string; message: string } | null>(null)
  const [keepTool, setKeepTool] = useState(true)
  const canvas = useRef<HTMLCanvasElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const gl = useRef<PictureGL | null>(null)
  const segmenter = useRef<Segmenter | null>(null)
  const coalesce = useRef<{ key: string | null; at: number }>({ key: null, at: 0 })
  const recipeNow = useRef(recipe)
  const shownMask = useRef<Mask | null>(null)
  const asking = useRef(new Set<string>())
  useEffect(() => { recipeNow.current = recipe })

  /** Change the recipe; edits with the same `key` within a moment are one undo step. */
  const update = useCallback((next: Recipe, key: string | null = null) => {
    const now = Date.now()
    const c = coalesce.current
    if (!(key && key === c.key && now - c.at < 800)) {
      setPast((p) => [...p.slice(-99), recipeNow.current])
      setFuture([])
    }
    coalesce.current = { key, at: now }
    setRecipe(normalizeRecipe(next))
  }, [])

  const undo = useCallback(() => {
    if (!past.length) return
    setFuture([recipe, ...future])
    setRecipe(past[past.length - 1])
    setPast(past.slice(0, -1))
    coalesce.current = { key: null, at: 0 }
  }, [past, future, recipe])
  const redo = useCallback(() => {
    if (!future.length) return
    setPast([...past, recipe])
    setRecipe(future[0])
    setFuture(future.slice(1))
    coalesce.current = { key: null, at: 0 }
  }, [past, future, recipe])

  // ── the cut-out model ────────────────────────────────────────────────────

  const startCutout = useCallback(async (from: Source) => {
    if (segmenter.current) return
    const s = new WorkerSegmenter()
    segmenter.current = s
    try {
      setSeg({ state: 'loading', done: 0, total: 0, message: null })
      await s.load((done, total) => setSeg((x) => ({ ...x, done, total })))
      setSeg((x) => ({ ...x, state: 'encoding' }))
      await s.encode(await createImageBitmap(from.bitmap), from.w, from.h)
      setSeg((x) => ({ ...x, state: 'ready' }))
    } catch (e) {
      s.dispose()
      segmenter.current = null
      setSeg({ state: 'error', done: 0, total: 0, message: errorText(e, 'The cut-out couldn’t start.') })
    }
  }, [])

  // The mask always follows the recipe's clicks: a click, undo, redo, Reset
  // all and reopening an edit all ask for (or find) the mask of what's there.
  const cutKey = recipe.cutout ? JSON.stringify(recipe.cutout.points) : ''
  useEffect(() => {
    const s = segmenter.current
    if (!cutKey || seg.state !== 'ready' || !s || masks.has(cutKey) || asking.current.has(cutKey) || maskError?.key === cutKey) return
    asking.current.add(cutKey)
    s.mask(JSON.parse(cutKey) as CutPoint[]).then((m) => {
      asking.current.delete(cutKey)
      setMasks((old) => {
        const next = new Map(old).set(cutKey, m)
        for (const k of next.keys()) if (next.size > MASKS_KEPT) next.delete(k)
        return next
      })
    }, (e) => {
      asking.current.delete(cutKey)
      setMaskError({ key: cutKey, message: errorText(e, 'The cut-out didn’t work on that click.') })
    })
  }, [cutKey, seg.state, masks, maskError])
  const mask = (cutKey && masks.get(cutKey)) || null
  const masking = !!cutKey && seg.state === 'ready' && !mask && maskError?.key !== cutKey

  // ── the picture ──────────────────────────────────────────────────────────

  useEffect(() => {
    let gone = false
    let opened: ImageBitmap | null = null
    ;(async () => {
      let id = reopened ? asset.parent! : asset.id
      let blob: Blob
      try {
        blob = await studioApi.pixels(siteId, id)
      } catch (e) {
        if (id === asset.id) throw e
        // Its source has left the library: edit this picture as it is.
        id = asset.id
        blob = await studioApi.pixels(siteId, id)
        if (!gone) setRecipe({})
      }
      opened = await createImageBitmap(blob)
      if (gone) { opened.close(); return }
      const s: Source = { bitmap: opened, w: opened.width, h: opened.height, png: blob.type !== 'image/jpeg', id }
      setSrc(s)
      setPhase('ready')
      if (startIn === 'cutout' || recipeNow.current.cutout) void startCutout(s)
    })().catch((e) => {
      if (!gone) { setPhase('error'); setError(errorText(e, 'Couldn’t open the picture.')) }
    })
    return () => {
      gone = true
      opened?.close()
      gl.current?.dispose()
      gl.current = null
      segmenter.current?.dispose()
      segmenter.current = null
    }
  }, [siteId, asset, reopened, startIn, startCutout])

  // The stage's size, for fitting the picture.
  useEffect(() => {
    const el = stage.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setBox({ w: Math.max(80, e.contentRect.width - 48), h: Math.max(80, e.contentRect.height - 48) }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // What is shown, and at what size on screen.
  const geo = recipe.crop ?? WHOLE
  const [frameW, frameH] = src ? (mode === 'crop' ? turned(src.w, src.h, geo.turn) : outputSize(src.w, src.h, recipe)) : [4, 3]
  const shown = fit(frameW, frameH, box)

  // Draw whenever anything shown changes.
  useEffect(() => {
    const el = canvas.current
    if (!src || !el) return
    if (!gl.current) {
      try {
        gl.current = new PictureGL(el)
        if (Math.max(src.w, src.h) > gl.current.maxSize) throw new Error('This picture is too large for this device to edit.')
        gl.current.setSource(src.bitmap, src.w, src.h)
      } catch (e) {
        requestAnimationFrame(() => { setPhase('error'); setError(errorText(e, 'This browser can’t edit pictures.')) })
        return
      }
    }
    const dpr = window.devicePixelRatio || 1
    const k = Math.min(dpr, PREVIEW_MAX / Math.max(shown.w, shown.h))
    if (shownMask.current !== mask) {
      gl.current.setMask(mask?.alpha ?? null, mask?.width, mask?.height)
      shownMask.current = mask
    }
    gl.current.draw(recipe, Math.round(shown.w * k), Math.round(shown.h * k), { before, uncropped: mode === 'crop' })
  }, [src, recipe, mode, before, mask, shown.w, shown.h])

  // The looks, drawn small once the picture is in.
  useEffect(() => {
    if (!src) return
    const id = requestAnimationFrame(() => {
      const c = document.createElement('canvas')
      let g: PictureGL | null = null
      try {
        g = new PictureGL(c)
        g.setSource(src.bitmap, src.w, src.h)
        const size = fit(src.w, src.h, { w: THUMB, h: THUMB })
        const out: Record<string, string> = {}
        for (const look of [null, ...LOOKS]) {
          g.draw(withLook({}, look), size.w, size.h)
          out[look?.key ?? 'original'] = c.toDataURL('image/jpeg', 0.8)
        }
        setThumbs(out)
      } catch {
        // No thumbnails: the names still work.
      } finally {
        g?.dispose()
      }
    })
    return () => cancelAnimationFrame(id)
  }, [src])

  // ── keys ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && (t as HTMLInputElement).type !== 'range') return
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return }
      if (e.key === '\\' && !e.repeat) setBefore(true)
    }
    const up = (e: KeyboardEvent) => { if (e.key === '\\') setBefore(false) }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
  }, [onClose, undo, redo])

  // ── saving ───────────────────────────────────────────────────────────────

  const done = async () => {
    if (!src) return
    const clean = normalizeRecipe(recipe)
    if (!Object.keys(clean).length) { onClose(); return }
    if (clean.cutout && !mask) {
      const failed = maskError?.key === cutKey || seg.state === 'error'
      setError(failed ? 'The cut-out didn’t work on those clicks: click again, or start the cut-out over.'
        : 'The cut-out is still being worked out: a moment.')
      return
    }
    setPhase('saving')
    setError(null)
    let g: PictureGL | null = null
    try {
      const [w, h] = outputSize(src.w, src.h, clean)
      const out = document.createElement('canvas')
      g = new PictureGL(out)
      g.setSource(src.bitmap, src.w, src.h)
      g.setMask(clean.cutout ? mask!.alpha : null, mask?.width, mask?.height)
      g.draw(clean, w, h)
      const type = clean.cutout || src.png ? 'image/png' : 'image/jpeg'
      const blob = await new Promise<Blob>((resolve, reject) =>
        out.toBlob((b) => (b ? resolve(b) : reject(new Error('Couldn’t draw the picture.'))), type, 0.92))
      onDone(await studioApi.saveEdit(siteId, src.id, blob, clean))
    } catch (e) {
      setPhase('ready')
      setError(errorText(e, 'Couldn’t save the edited picture.'))
    } finally {
      g?.dispose()
    }
  }

  // ── crop ─────────────────────────────────────────────────────────────────

  const setCrop = (c: Partial<Crop>, key: string | null = null) => update({ ...recipe, crop: { ...geo, ...c } }, key)

  const chooseAspect = (key: string) => {
    setAspect(key)
    const a = ASPECTS.find((x) => x.key === key)
    if (!src || !a || a.ratio === null) return
    const [tw, th] = turned(src.w, src.h, geo.turn)
    const ratio = a.ratio || src.w / src.h
    // The largest box of that shape, centred.
    let w = 1, h = (tw / ratio) / th
    if (h > 1) { h = 1; w = (ratio * th) / tw }
    setCrop({ x: (1 - w) / 2, y: (1 - h) / 2, w, h })
  }

  const dragCrop = (handle: string) => (e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!src) return
    const start = { ...geo }
    const x0 = e.clientX, y0 = e.clientY
    const [tw, th] = turned(src.w, src.h, geo.turn)
    const a = ASPECTS.find((x) => x.key === aspect)
    const ratio = a && a.ratio !== null ? (a.ratio || src.w / src.h) * (th / tw) : null // w / h in fractions
    const el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - x0) / shown.w, dy = (ev.clientY - y0) / shown.h
      let { x, y, w, h } = start
      if (handle === 'move') {
        x = clamp(x + dx, 0, 1 - w)
        y = clamp(y + dy, 0, 1 - h)
      } else {
        const right = x + w, bottom = y + h
        if (handle.includes('w')) x = clamp(x + dx, 0, right - CROP_MIN)
        if (handle.includes('e')) w = clamp(w + dx, CROP_MIN, 1 - x)
        if (handle.includes('n')) y = clamp(y + dy, 0, bottom - CROP_MIN)
        if (handle.includes('s')) h = clamp(h + dy, CROP_MIN, 1 - y)
        if (handle.includes('w')) w = right - x
        if (handle.includes('n')) h = bottom - y
        if (ratio) {
          h = clamp(w / ratio, CROP_MIN, handle.includes('n') ? bottom : 1 - y)
          w = h * ratio
          if (handle.includes('w')) x = right - w
          if (handle.includes('n')) y = bottom - h
        }
      }
      setCrop({ x, y, w, h }, 'crop-drag')
    }
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); coalesce.current.key = null }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }

  const turn = (by: 90 | -90) => {
    const next = (((geo.turn + by) % 360) + 360) % 360 as Crop['turn']
    update({ ...recipe, crop: { ...WHOLE, angle: geo.angle, flip_h: geo.flip_h, flip_v: geo.flip_v, turn: next } })
    setAspect('free')
  }

  // ── cut-out ──────────────────────────────────────────────────────────────

  const click = (e: React.PointerEvent) => {
    if (mode !== 'cutout' || seg.state !== 'ready' || !src) return
    const r = e.currentTarget.getBoundingClientRect()
    const p = sourceUv((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height, src.w, src.h, geo)
    if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) return
    const old = recipe.cutout?.points ?? []
    if (old.length >= MAX_POINTS) return
    const points = [...old, { x: p.x, y: p.y, keep: keepTool && !e.altKey }]
    update({ ...recipe, cutout: { feather: recipe.cutout?.feather ?? 0, invert: recipe.cutout?.invert ?? false, points } })
  }

  const setCut = (patch: { feather?: number; invert?: boolean }, key: string | null = null) => {
    if (!recipe.cutout) return
    update({ ...recipe, cutout: { ...recipe.cutout, ...patch } }, key)
  }

  const clearCut = () => update({ ...recipe, cutout: undefined })

  const openTab = (m: Mode) => {
    setMode(m)
    if (m === 'cutout' && src && seg.state === 'off') void startCutout(src)
  }

  // ── view ─────────────────────────────────────────────────────────────────

  const changed = Object.keys(normalizeRecipe(recipe)).length > 0
  const busy = phase !== 'ready'
  const points = recipe.cutout?.points ?? []

  return (
    <div className="studio-dark fixed inset-0 z-50 flex select-none flex-col bg-zinc-950 text-zinc-100" role="dialog" aria-modal="true" aria-label="Edit picture">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-800 px-3">
        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">Picture</span>
        <span className="min-w-0 truncate text-sm text-zinc-300">{asset.credit_line || asset.alt || 'Edit picture'}</span>
        <div className="ml-4 flex items-center gap-1">
          <TopBtn title="Undo (⌘Z)" onClick={undo} disabled={!past.length}><Undo2 className="h-4 w-4" /></TopBtn>
          <TopBtn title="Redo (⇧⌘Z)" onClick={redo} disabled={!future.length}><Redo2 className="h-4 w-4" /></TopBtn>
          <button type="button" title="Hold to see the picture as it was (or hold \)" disabled={busy}
            onPointerDown={() => setBefore(true)} onPointerUp={() => setBefore(false)} onPointerLeave={() => setBefore(false)}
            className={`ml-1 rounded-md border px-2.5 py-1 text-xs ${before ? 'border-emerald-500 text-emerald-300' : 'border-zinc-700 text-zinc-300 hover:border-zinc-500'}`}>
            Before
          </button>
          <button type="button" onClick={() => { update({}); setAspect('free') }} disabled={busy || !changed}
            className="rounded-md px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40">Reset all</button>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {error && <span role="alert" className="max-w-md truncate text-xs text-red-300" title={error}>{error}</span>}
          {onHelp && (
            <button type="button" onClick={() => onHelp(mode === 'cutout' ? 'cutout' : 'picture')} aria-label="How the Picture Editor works"
              title="How the Picture Editor works" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><CircleHelp className="h-4 w-4" /></button>
          )}
          <button type="button" onClick={onClose} disabled={phase === 'saving'} className="rounded-md px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800">Cancel</button>
          <button type="button" onClick={() => void done()} disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
            {phase === 'saving' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{phase === 'saving' ? 'Saving…' : 'Done'}
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside aria-label="Looks" className="w-[236px] shrink-0 overflow-y-auto border-r border-zinc-800 bg-zinc-900 p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Looks</h3>
          <div className="grid grid-cols-2 gap-2">
            {[{ key: 'original', label: 'Original' }, ...LOOKS].map((l) => {
              const on = (recipe.look ?? 'original') === l.key
              return (
                <button key={l.key} type="button" disabled={busy} aria-pressed={on}
                  onClick={() => update(withLook(recipe, LOOKS.find((x) => x.key === l.key) ?? null))}
                  className={`overflow-hidden rounded-md border text-left ${on ? 'border-emerald-500' : 'border-zinc-800 hover:border-zinc-600'}`}>
                  <span className="flex h-20 items-center justify-center bg-zinc-950">
                    {thumbs[l.key] ? <img src={thumbs[l.key]} alt="" className="max-h-full max-w-full" /> : <span className="h-full w-full animate-pulse bg-zinc-800" />}
                  </span>
                  <span className="block truncate px-1.5 py-1 text-[11px] text-zinc-300">{l.label}</span>
                </button>
              )
            })}
          </div>
        </aside>

        <div ref={stage} className="relative flex min-w-0 flex-1 items-center justify-center bg-[#2b2b2e]">
          {phase === 'loading' && <p className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" />Opening the picture…</p>}
          {phase === 'error' && !src && <p role="alert" className="max-w-sm text-center text-sm text-red-300">{error}</p>}
          <div className={`relative ${src ? '' : 'hidden'}`} style={{ width: shown.w, height: shown.h }}>
            <div className="absolute inset-0" style={recipe.cutout && !before ? CHECKER : undefined} />
            <canvas ref={canvas} data-picture-canvas className="absolute inset-0 h-full w-full" />
            {mode === 'crop' && src && <CropBox crop={geo} onDrag={dragCrop} />}
            {mode === 'cutout' && (
              <div className={`absolute inset-0 ${seg.state === 'ready' ? 'cursor-crosshair' : ''}`} onPointerDown={click} data-cutout-target>
                {src && points.map((p, k) => {
                  const o = outputUv(p.x, p.y, src.w, src.h, geo)
                  return <span key={k} className={`pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow ${p.keep ? 'bg-emerald-500' : 'bg-red-500'}`}
                    style={{ left: `${o.x * 100}%`, top: `${o.y * 100}%` }} />
                })}
              </div>
            )}
            {masking && <span className="absolute right-2 top-2 flex items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] text-zinc-200"><Loader2 className="h-3 w-3 animate-spin" />Cutting out…</span>}
          </div>
        </div>

        <aside aria-label="Picture controls" className="flex w-[300px] shrink-0 flex-col border-l border-zinc-800 bg-zinc-900">
          <div role="tablist" aria-label="Tools" className="flex border-b border-zinc-800 p-1">
            {(['adjust', 'crop', 'cutout'] as const).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m} disabled={busy} onClick={() => openTab(m)}
                className={`flex-1 rounded-md py-1.5 text-xs ${mode === m ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-zinc-100'}`}>
                {m === 'adjust' ? 'Adjust' : m === 'crop' ? 'Crop' : 'Cut out'}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {mode === 'adjust' && (
              <>
                {GROUPS.map((g) => (
                  <Group key={g.title} title={g.title}>
                    {g.sliders.map((s) => (
                      <Range key={s.key} label={s.label} value={recipe[s.key] ?? 0} min={s.min} max={s.max} step={s.step ?? 1} hue={s.hue}
                        onChange={(v) => update({ ...recipe, [s.key]: v }, s.key)} />
                    ))}
                    {g.title === 'Colour' && (
                      <label className="flex items-center gap-2 pt-1 text-xs text-zinc-300">
                        <input type="checkbox" checked={!!recipe.bw} onChange={(e) => update({ ...recipe, bw: e.target.checked })} className="accent-emerald-500" />
                        Black and white
                      </label>
                    )}
                  </Group>
                ))}
              </>
            )}
            {mode === 'crop' && (
              <>
                <Group title="Shape">
                  <div className="grid grid-cols-4 gap-1">
                    {ASPECTS.map((a) => (
                      <button key={a.key} type="button" aria-pressed={aspect === a.key} onClick={() => chooseAspect(a.key)}
                        className={`rounded-md py-1 text-[11px] ${aspect === a.key ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'}`}>{a.label}</button>
                    ))}
                  </div>
                </Group>
                <Group title="Straighten">
                  <Range label="Angle" value={geo.angle} min={-ANGLE_MAX} max={ANGLE_MAX} step={0.1} unit="°" onChange={(v) => setCrop({ angle: v }, 'angle')} />
                  <div className="flex gap-1 pt-1">
                    <TopBtn title="Turn left" onClick={() => turn(-90)}><RotateCcw className="h-4 w-4" /></TopBtn>
                    <TopBtn title="Turn right" onClick={() => turn(90)}><RotateCw className="h-4 w-4" /></TopBtn>
                    <TopBtn title="Flip across" onClick={() => setCrop({ flip_h: !geo.flip_h })} active={geo.flip_h}><FlipHorizontal2 className="h-4 w-4" /></TopBtn>
                    <TopBtn title="Flip upside down" onClick={() => setCrop({ flip_v: !geo.flip_v })} active={geo.flip_v}><FlipVertical2 className="h-4 w-4" /></TopBtn>
                  </div>
                </Group>
                <div className="px-4 py-3">
                  <p className="mb-2 text-[11px] text-zinc-500">Drag the box’s corners and sides, or inside it to move it.</p>
                  <button type="button" disabled={!recipe.crop} onClick={() => { update({ ...recipe, crop: undefined }); setAspect('free') }}
                    className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-40">Reset the crop</button>
                </div>
              </>
            )}
            {mode === 'cutout' && (
              <CutPanel seg={seg} clickError={maskError?.key === cutKey ? maskError.message : null} hasCut={!!recipe.cutout} points={points.length} keepTool={keepTool} setKeepTool={setKeepTool}
                feather={recipe.cutout?.feather ?? 0} invert={!!recipe.cutout?.invert} onFeather={(v) => setCut({ feather: v }, 'feather')}
                onInvert={(v) => setCut({ invert: v })} onClear={clearCut}
                onRetry={() => { if (src) { setSeg({ state: 'off', done: 0, total: 0, message: null }); void startCutout(src) } }} />
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

const CHECKER = {
  backgroundImage: 'linear-gradient(45deg,#3f3f46 25%,transparent 25%),linear-gradient(-45deg,#3f3f46 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#3f3f46 75%),linear-gradient(-45deg,transparent 75%,#3f3f46 75%)',
  backgroundSize: '16px 16px', backgroundPosition: '0 0,0 8px,8px -8px,-8px 0', backgroundColor: '#27272a',
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="border-b border-zinc-800 px-4 py-3">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
      <div className="space-y-1.5">{children}</div>
    </section>
  )
}

function TopBtn({ title, onClick, disabled, active, children }: { title: string; onClick: () => void; disabled?: boolean; active?: boolean; children: ReactNode }) {
  return (
    <button type="button" title={title} aria-label={title} aria-pressed={active} onClick={onClick} disabled={disabled}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-md disabled:opacity-30 ${active ? 'bg-emerald-500/20 text-emerald-300' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'}`}>
      {children}
    </button>
  )
}

/** A slider, Lightroom's way: its value beside it, double-click the name to put it back. */
function Range({ label, value, min, max, step, unit = '', hue, onChange }: {
  label: string; value: number; min: number; max: number; step: number; unit?: string; hue?: boolean; onChange: (v: number) => void
}) {
  const track = hue ? { background: 'linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)' } : undefined
  return (
    <div className="flex items-center gap-2 text-xs">
      <span onDoubleClick={() => onChange(0)} title="Double-click to put it back" className="w-[86px] shrink-0 cursor-default truncate text-zinc-400">{label}</span>
      <input type="range" aria-label={label} min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 min-w-0 flex-1 cursor-pointer appearance-auto rounded accent-emerald-500" style={track} />
      <span className={`w-11 text-right tabular-nums ${value ? 'text-zinc-100' : 'text-zinc-500'}`}>{step < 1 && value > 0 ? '+' : ''}{step < 1 ? value.toFixed(step < 0.1 ? 2 : 1) : value}{unit}</span>
    </div>
  )
}

const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'] as const
const HANDLE_AT: Record<(typeof HANDLES)[number], string> = {
  nw: 'left-0 top-0 cursor-nwse-resize', n: 'left-1/2 top-0 cursor-ns-resize', ne: 'left-full top-0 cursor-nesw-resize',
  e: 'left-full top-1/2 cursor-ew-resize', se: 'left-full top-full cursor-nwse-resize', s: 'left-1/2 top-full cursor-ns-resize',
  sw: 'left-0 top-full cursor-nesw-resize', w: 'left-0 top-1/2 cursor-ew-resize',
}

/** The crop box over the whole frame: the rest dimmed, thirds drawn, handles to drag. */
function CropBox({ crop, onDrag }: { crop: Crop; onDrag: (handle: string) => (e: React.PointerEvent) => void }) {
  return (
    <div data-crop-box onPointerDown={onDrag('move')} className="absolute cursor-move border border-white/90"
      style={{ left: `${crop.x * 100}%`, top: `${crop.y * 100}%`, width: `${crop.w * 100}%`, height: `${crop.h * 100}%`,
        boxShadow: '0 0 0 9999px rgba(0,0,0,.55)' }}>
      <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3">
        {Array.from({ length: 9 }, (_, k) => <span key={k} className="border border-white/20" />)}
      </div>
      {HANDLES.map((h) => (
        <span key={h} data-crop-handle={h} onPointerDown={onDrag(h)}
          className={`absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-zinc-900 bg-white ${HANDLE_AT[h]}`} />
      ))}
    </div>
  )
}

function CutPanel({ seg, clickError, hasCut, points, keepTool, setKeepTool, feather, invert, onFeather, onInvert, onClear, onRetry }: {
  seg: Seg; clickError: string | null; hasCut: boolean; points: number; keepTool: boolean; setKeepTool: (v: boolean) => void; feather: number; invert: boolean
  onFeather: (v: number) => void; onInvert: (v: boolean) => void; onClear: () => void; onRetry: () => void
}) {
  if (seg.state === 'off' || seg.state === 'loading' || seg.state === 'encoding') {
    const mb = (n: number) => (n / 1e6).toFixed(1)
    return (
      <div className="space-y-3 px-4 py-4 text-xs text-zinc-300">
        <p>Click what to keep, and the Studio cuts it out of its background, right here in your browser.</p>
        <div role="status" className="space-y-1.5">
          <p className="flex items-center gap-2 text-zinc-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />
            {seg.state === 'encoding' ? 'Looking at the picture…' : seg.total ? `Getting the cut-out model… ${mb(seg.done)} of ${mb(seg.total)} MB` : 'Getting the cut-out model…'}</p>
          {seg.state === 'loading' && seg.total > 0 && (
            <div className="h-1 overflow-hidden rounded bg-zinc-800"><div className="h-full bg-emerald-500" style={{ width: `${(seg.done / seg.total) * 100}%` }} /></div>
          )}
          <p className="text-[11px] text-zinc-500">The first time, this downloads about 14 MB.</p>
        </div>
      </div>
    )
  }
  if (seg.state === 'error') {
    return (
      <div className="space-y-2 px-4 py-4 text-xs">
        <p role="alert" className="text-red-300">{seg.message}</p>
        <button type="button" onClick={onRetry} className="rounded-md border border-zinc-700 px-2.5 py-1 text-zinc-300 hover:border-zinc-500">Try again</button>
      </div>
    )
  }
  return (
    <>
      <Group title="Cut out">
        <p className="text-xs text-zinc-300">{points ? 'Click more to add to it, or to take away (Alt-click).' : 'Click what to keep.'}</p>
        <div className="flex rounded-md border border-zinc-800 p-0.5" role="group" aria-label="Clicks">
          {[true, false].map((k) => (
            <button key={String(k)} type="button" aria-pressed={keepTool === k} onClick={() => setKeepTool(k)}
              className={`flex h-6 flex-1 items-center justify-center gap-1.5 rounded text-[11px] ${keepTool === k ? 'bg-zinc-700 text-zinc-50' : 'text-zinc-400 hover:text-zinc-100'}`}>
              <span className={`h-2 w-2 rounded-full ${k ? 'bg-emerald-500' : 'bg-red-500'}`} />{k ? 'Keep' : 'Take away'}
            </button>
          ))}
        </div>
        {clickError && <p role="alert" className="text-[11px] text-red-300">{clickError}</p>}
      </Group>
      {hasCut && (
        <Group title="Edge">
          <Range label="Feather" value={feather} min={0} max={FEATHER_MAX} step={1} onChange={onFeather} />
          <label className="flex items-center gap-2 pt-1 text-xs text-zinc-300">
            <input type="checkbox" checked={invert} onChange={(e) => onInvert(e.target.checked)} className="accent-emerald-500" />
            Keep the background instead
          </label>
          <button type="button" onClick={onClear} className="mt-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500">
            <X className="mr-1 inline h-3 w-3" />Start over
          </button>
        </Group>
      )}
    </>
  )
}
