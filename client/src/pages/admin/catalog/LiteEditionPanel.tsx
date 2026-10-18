/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminTab, AdminTabBar } from '../../../components/admin/AdminTabs'
import { AdminButton as Button, AdminCard, AdminInput, AdminTextarea } from '../../../components/admin/AdminUI'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Download, FileText, PencilLine } from 'lucide-react'

import { api } from '../../../api/client'
import { getTemplate, saveTemplate } from '../../../api/admin/dealTemplates'
import SaveTemplateButton from '../sales/SaveTemplateButton'

type Block = { id: string; kind: string; text: string; items: string[]; new_page: boolean; column: string }

const COMPUTED_LABEL: Record<string, string> = { card: 'Price card (auto from pricing)' }
const EDITABLE = new Set(['lead', 'h2', 'h3', 'h2c', 'p', 'pc', 'bullets'])

export default function LiteEditionPanel({
  baseInputs,
  validHeadcount,
  filenameBase,
}: {
  baseInputs: Record<string, unknown>
  validHeadcount: boolean
  filenameBase: string
}) {
  const [blocks, setBlocks] = useState<Block[] | null>(null)
  const [view, setView] = useState<'edit' | 'preview'>('edit')
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<{ blocks: Block[] }>('/admin/deal-flow/lite-defaults'),
      getTemplate<{ blocks: Block[] }>('lite'),
    ])
      .then(([def, saved]) => setBlocks(saved.payload?.blocks ?? def.blocks))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load template'))
  }, [])

  const payload = useMemo(
    () => ({
      ...baseInputs,
      template: 'lite_edition',
      lite_blocks: blocks
        ? blocks.map((b) => (b.kind === 'bullets' ? { ...b, items: b.items.filter((i) => i.trim()) } : b))
        : null,
    }),
    [baseInputs, blocks],
  )

  const payloadRef = useRef(payload)
  useEffect(() => { payloadRef.current = payload }, [payload])
  useEffect(() => {
    if (view !== 'preview' || !validHeadcount) return
    setPreviewing(true)
    const t = setTimeout(() => {
      api.post<{ html: string }>('/admin/deal-flow/proposal/preview', payloadRef.current)
        .then((r) => { setPreviewHtml(r.html); setError(null) })
        .catch((e) => setError(e instanceof Error ? e.message : 'Preview failed'))
        .finally(() => setPreviewing(false))
    }, 300)
    return () => clearTimeout(t)
  }, [view, payload, validHeadcount])

  function updateBlock(id: string, patch: Partial<Block>) {
    setBlocks((prev) => prev && prev.map((b) => (b.id === id ? { ...b, ...patch } : b)))
  }

  async function saveTpl() {
    // Lite Edition's template is its editable copy; pricing comes from the one-pager inputs.
    await saveTemplate<{ blocks: Block[] }>('lite', { blocks: blocks ?? [] })
  }

  async function download() {
    if (!validHeadcount) return
    setDownloading(true)
    setError(null)
    try {
      const safe = (filenameBase.trim() || 'Matcha').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
      await api.downloadPost('/admin/deal-flow/proposal', payload, `${safe}_Matcha_Lite.pdf`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <AdminTabBar className="mb-0!" role="group" aria-label="View">
          <AdminTab active={view === 'edit'} onClick={() => setView('edit')}><PencilLine className="h-3.5 w-3.5" />Edit</AdminTab>
          <AdminTab active={view === 'preview'} onClick={() => setView('preview')}><FileText className="h-3.5 w-3.5" />Preview</AdminTab>
        </AdminTabBar>
        <div className="flex items-center gap-2">
          <SaveTemplateButton onSave={saveTpl} />
          <Button onClick={download} disabled={!validHeadcount || downloading}>
            {downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Download Lite PDF
          </Button>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      <div className="mt-4">
        {view === 'preview' ? (
          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-200">
            {previewing && (
              <div className="flex items-center gap-2 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400">
                <Loader2 className="h-3 w-3 animate-spin" /> Rendering…
              </div>
            )}
            <iframe title="lite preview" sandbox="" srcDoc={previewHtml} className="h-[80vh] w-full bg-white" />
          </div>
        ) : !blocks ? (
          <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading template…</p>
        ) : (
          <AdminCard className="max-w-[560px] space-y-2.5">
            <p className="text-xs text-zinc-500">Edit the Lite copy. The price card fills from the pricing inputs at left. Preview to see the styled one-pager.</p>
            {blocks.map((b) => (
              <BlockEditor key={b.id} block={b} onChange={(patch) => updateBlock(b.id, patch)} />
            ))}
          </AdminCard>
        )}
      </div>
    </div>
  )
}

function BlockEditor({ block, onChange }: { block: Block; onChange: (patch: Partial<Block>) => void }) {
  if (!EDITABLE.has(block.kind)) {
    return (
      <div className="rounded-md border border-dashed border-zinc-700 bg-zinc-800/40 px-3 py-2 text-xs italic text-zinc-500">
        ▦ {COMPUTED_LABEL[block.kind] ?? block.kind}
      </div>
    )
  }
  if (block.kind === 'h2' || block.kind === 'h3' || block.kind === 'h2c') {
    const size = block.kind === 'h3' ? 'text-base font-semibold' : 'text-sm font-semibold uppercase tracking-wide text-amber-300/80'
    return (
      <AdminInput
        value={block.text}
        onChange={(e) => onChange({ text: e.target.value })}
        className={` border-transparent bg-transparent ${size}`}
      />
    )
  }
  if (block.kind === 'bullets') {
    return (
      <AutoTextarea value={block.items.join('\n')} onChange={(v) => onChange({ items: v.split('\n') })}
        className="text-sm text-zinc-300" placeholder="One bullet per line — &quot;Label: text&quot;" />
    )
  }
  const cls = block.kind === 'lead' ? 'text-sm italic text-zinc-200' : 'text-sm text-zinc-300'
  return <AutoTextarea value={block.text} onChange={(v) => onChange({ text: v })} className={cls} />
}

function AutoTextarea({
  value, onChange, className = '', placeholder,
}: { value: string; onChange: (v: string) => void; className?: string; placeholder?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px` }
  }, [value])
  return (
    <AdminTextarea
      ref={ref}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      rows={1}
      className={` resize-none border-transparent bg-transparent leading-relaxed ${className}`}
    />
  )
}
