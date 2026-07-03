import { useContext, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Film, ImagePlus, Loader2, Plus, Trash2 } from 'lucide-react'
import { cappeApi } from '../../../../api/cappeClient'
import { useCappeMe } from '../../../../hooks/useCappeMe'
import { SiteCtx } from './context'
import { inputCls } from './styles'
import type { Field } from './types'
import { arr, isOn, obj, str } from './valueHelpers'

export function ImageInput({ value, onChange }: { value: unknown; onChange: (v: string) => void }) {
  const siteId = useContext(SiteCtx)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const url = str(value)

  async function upload(file: File) {
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}/upload`, fd)
      onChange(res.url)
    } catch {
      /* surfaced by empty url */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input value={url} onChange={(e) => onChange(e.target.value)} placeholder="Image URL" className={inputCls} />
      {url && <img src={url} alt="" className="h-9 w-9 shrink-0 rounded object-cover" />}
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={busy}
        className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
      />
    </div>
  )
}

export function VideoInput({ value, onChange }: { value: unknown; onChange: (v: string) => void }) {
  const siteId = useContext(SiteCtx)
  const { account } = useCappeMe()
  const premium = account?.plan === 'pro' || account?.plan === 'business'
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const url = str(value)

  async function upload(file: File) {
    setBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}/upload-video`, fd)
      onChange(res.url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  if (!premium) {
    return (
      <div className="rounded-lg border border-dashed border-amber-700/40 bg-amber-500/[0.06] px-3 py-2.5 text-xs text-amber-300/90">
        <span className="font-medium">Premium feature.</span> Upgrade to Pro to add an autoplay background video to your hero.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2">
        <input value={url} onChange={(e) => onChange(e.target.value)} placeholder="Video URL (MP4 / WebM)" className={inputCls} />
        {url && <video src={url} muted playsInline className="h-9 w-14 shrink-0 rounded object-cover" />}
        {url && (
          <button type="button" onClick={() => onChange('')} className="shrink-0 text-zinc-500 hover:text-red-400" title="Clear">
            <Trash2 className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Film className="h-3.5 w-3.5" />}
        </button>
      </div>
      {err && <p className="mt-1 text-xs text-red-400">{err}</p>}
      <p className="mt-1 text-[11px] text-zinc-500">Short, muted loop works best (MP4/WebM, max 50 MB). Set a Hero photo above to use as the poster.</p>
      <input
        ref={fileRef}
        type="file"
        accept="video/mp4,video/webm,video/quicktime"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
      />
    </div>
  )
}

export function StringList({ value, onChange }: { value: unknown; onChange: (v: string[]) => void }) {
  const items = arr(value).map(str)
  const set = (i: number, v: string) => onChange(items.map((x, j) => (j === i ? v : x)))
  return (
    <div className="space-y-1.5">
      {items.map((v, i) => (
        <div key={i} className="flex gap-1.5">
          <input value={v} onChange={(e) => set(i, e.target.value)} className={inputCls} />
          <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="px-2 text-zinc-500 hover:text-red-400">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...items, ''])} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">
        + Add
      </button>
    </div>
  )
}

export function ListEditor({ field, value, onChange }: { field: Field; value: unknown; onChange: (v: unknown[]) => void }) {
  const rows = arr(value)
  const setRow = (i: number, row: Record<string, unknown>) => onChange(rows.map((r, j) => (j === i ? row : r)))
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const next = [...rows]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  return (
    <div className="space-y-3">
      {rows.map((r, i) => {
        const row = obj(r)
        return (
          <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                {field.label.replace(/s$/, '')} {i + 1}
              </span>
              <div className="flex items-center gap-1 text-zinc-500">
                <button type="button" onClick={() => move(i, -1)} className="hover:text-zinc-200"><ChevronUp className="h-3.5 w-3.5" /></button>
                <button type="button" onClick={() => move(i, 1)} className="hover:text-zinc-200"><ChevronDown className="h-3.5 w-3.5" /></button>
                <button type="button" onClick={() => onChange(rows.filter((_, j) => j !== i))} className="hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
            <div className="space-y-2.5">
              {(field.item || []).map((sf) => (
                <FieldInput key={sf.key} field={sf} value={row[sf.key]} onChange={(v) => setRow(i, { ...row, [sf.key]: v })} />
              ))}
            </div>
          </div>
        )
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, field.newItem ? field.newItem() : {}])}
        className="inline-flex items-center gap-1 rounded-lg border border-dashed border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400"
      >
        <Plus className="h-3.5 w-3.5" /> {field.addLabel || 'Add'}
      </button>
    </div>
  )
}

export function FieldInput({ field, value, onChange }: { field: Field; value: unknown; onChange: (v: unknown) => void }) {
  const label = (
    <label className="mb-1 block text-xs font-medium text-zinc-400">{field.label}</label>
  )
  if (field.kind === 'list') {
    return <div>{label}<ListEditor field={field} value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'strlist') {
    return <div>{label}<StringList value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'image') {
    return <div>{label}<ImageInput value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'video') {
    return <div>{label}<VideoInput value={value} onChange={onChange} /></div>
  }
  if (field.kind === 'bool') {
    return (
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={isOn(value)} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500" />
        {field.label}
      </label>
    )
  }
  if (field.kind === 'select') {
    return (
      <div>{label}
        <select value={str(value)} onChange={(e) => onChange(e.target.value)} className={inputCls}>
          {(field.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
    )
  }
  if (field.kind === 'textarea') {
    return <div>{label}<textarea value={str(value)} onChange={(e) => onChange(e.target.value)} rows={3} placeholder={field.placeholder} className={inputCls} /></div>
  }
  return <div>{label}<input value={str(value)} onChange={(e) => onChange(e.target.value)} placeholder={field.placeholder} className={inputCls} /></div>
}
