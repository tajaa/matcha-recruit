import { useLayoutEffect, useRef } from 'react'
import { ArrowDown, ArrowUp, FilePlus2, Trash2 } from 'lucide-react'
import { ColorField, IconBtn, NumberField, Row, Section, Select } from '../../../magazine/workspace/controls'
import { PAGE_PRESETS, pageSide, spreads } from '../../model/doc'
import { LIMITS } from '../../model/limits'
import { addPages, deletePage, movePage } from '../../model/ops'
import type { Doc, Units } from '../../model/types'
import { UNIT_LABEL } from '../../model/units'
import { frameThreads, pageItemsHtml, type Draw } from '../../render/layoutRender'
import { setHtml } from '../../render/sink'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'
import { LengthField, Labeled } from '../fields'

const THUMB = 56 // a page thumbnail's width, px

/** The pages, as spreads of thumbnails: click one to go to it. Add, delete
 *  and reorder pages; set the document's size, facing pages, margins,
 *  columns and grids. */
export function PagesPanel() {
  const c = useCtx()
  const { store } = c
  const doc = useStudio(store, (s) => s.doc)
  const page = useStudio(store, (s) => s.page)
  const live = c.post.access === 'paid'
  const go = (i: number) => { store.set({ page: i }); c.fit(i, true) }
  return (
    <>
      <Section title={`Pages · ${doc.pages.length}`} right={
        <div className="flex">
          <IconBtn title="Add a page after this one" onClick={() => store.edit((d) => addPages(d, page), { extra: { page: page + 1 } })}
            disabled={doc.pages.length >= LIMITS.MAX_PAGES}><FilePlus2 className="h-3.5 w-3.5" /></IconBtn>
          <IconBtn title="Move this page earlier" disabled={page === 0}
            onClick={() => store.edit((d) => movePage(d, page, page - 1), { extra: { page: page - 1 } })}><ArrowUp className="h-3.5 w-3.5" /></IconBtn>
          <IconBtn title="Move this page later" disabled={page >= doc.pages.length - 1}
            onClick={() => store.edit((d) => movePage(d, page, page + 1), { extra: { page: page + 1 } })}><ArrowDown className="h-3.5 w-3.5" /></IconBtn>
          <IconBtn title="Delete this page and what is on it" disabled={doc.pages.length <= 1}
            onClick={() => store.edit((d) => deletePage(d, page), { extra: { selection: [], page: Math.max(0, page - 1) } })}>
            <Trash2 className="h-3.5 w-3.5" /></IconBtn>
        </div>
      }>
        <Thumbs doc={doc} page={page} onGo={go} />
      </Section>
      <DocumentSetup doc={doc} paid={live} />
    </>
  )
}

function Thumbs({ doc, page, onGo }: { doc: Doc; page: number; onGo: (i: number) => void }) {
  const { store, fonts } = useCtx()
  const assets = useStudio(store, (s) => s.assets)
  const els = useRef<(HTMLDivElement | null)[]>([])
  const scale = THUMB / doc.size.w
  useLayoutEffect(() => {
    const d: Draw = { assets, faces: fonts.book.face, used: new Map(), threads: frameThreads(doc) }
    doc.pages.forEach((_, i) => { const el = els.current[i]; if (el) setHtml(el, pageItemsHtml(doc, i, d)) })
  }, [doc, assets, fonts])
  return (
    <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
      {spreads(doc).map((pages) => (
        <div key={pages[0]} className={`flex ${doc.facing && pages.length === 1 && pageSide(doc, pages[0]) === 'right' ? 'justify-end pr-[calc(50%-56px)]' : 'justify-center'}`}>
          {pages.map((i) => (
            <button key={doc.pages[i].id} type="button" onClick={() => onGo(i)} aria-label={`Page ${i + 1}`} aria-current={i === page}
              className={`group relative flex flex-col items-center ${i === page ? '' : 'opacity-80 hover:opacity-100'}`}>
              <div className={`relative overflow-hidden outline outline-2 ${i === page ? 'outline-emerald-500' : 'outline-transparent'}`}
                style={{ width: THUMB, height: doc.size.h * scale, background: doc.paper, ['--u' as string]: `${scale}px` }}>
                <div ref={(el) => { els.current[i] = el }} className="absolute inset-0" />
                {doc.paywall_page !== null && i + 1 >= doc.paywall_page && (
                  <span className="absolute right-0.5 top-0.5 rounded bg-black/60 px-1 text-[8px] text-amber-300">$</span>
                )}
              </div>
              <span className="mt-0.5 text-[10px] tabular-nums text-zinc-500">{i + 1}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}

const UNITS = (Object.keys(UNIT_LABEL) as Units[]).map((k) => ({ key: k, label: UNIT_LABEL[k] }))

function DocumentSetup({ doc, paid }: { doc: Doc; paid: boolean }) {
  const { store } = useCtx()
  const set = (patch: Partial<Doc>, key?: string) => store.edit((d) => ({ ...d, ...patch }), { key: key ?? null })
  const preset = PAGE_PRESETS.find((p) => Math.abs(p.w - doc.size.w) < 0.5 && Math.abs(p.h - doc.size.h) < 0.5)?.key ?? 'custom'
  const u = doc.units
  return (
    <Section title="Document">
      <Select label="Page size" value={preset} options={[...PAGE_PRESETS.map((p) => ({ key: p.key, label: p.label })), { key: 'custom', label: 'Custom' }]}
        onChange={(k) => { const p = PAGE_PRESETS.find((x) => x.key === k); if (p) set({ size: { w: p.w, h: p.h } }) }} />
      <Row>
        <LengthField label="Page width" short="W" units={u} value={doc.size.w} min={LIMITS.PAGE_MIN} max={LIMITS.PAGE_MAX}
          onChange={(w) => set({ size: { ...doc.size, w } })} />
        <LengthField label="Page height" short="H" units={u} value={doc.size.h} min={LIMITS.PAGE_MIN} max={LIMITS.PAGE_MAX}
          onChange={(h) => set({ size: { ...doc.size, h } })} />
      </Row>
      <label className="flex items-center gap-2 text-xs text-zinc-300">
        <input type="checkbox" checked={doc.facing} onChange={(e) => set({ facing: e.target.checked })} className="accent-emerald-500" />
        Facing pages (spreads)
      </label>
      <Labeled label="Margins">
        <Row>
          <LengthField label="Top margin" short="↑" units={u} value={doc.margins.t} min={0} onChange={(t) => set({ margins: { ...doc.margins, t } })} />
          <LengthField label="Bottom margin" short="↓" units={u} value={doc.margins.b} min={0} onChange={(b) => set({ margins: { ...doc.margins, b } })} />
        </Row>
      </Labeled>
      <Row>
        <LengthField label={doc.facing ? 'Inside margin' : 'Left margin'} short={doc.facing ? 'In' : '←'} units={u} value={doc.margins.i} min={0}
          onChange={(i) => set({ margins: { ...doc.margins, i } })} />
        <LengthField label={doc.facing ? 'Outside margin' : 'Right margin'} short={doc.facing ? 'Out' : '→'} units={u} value={doc.margins.o} min={0}
          onChange={(o) => set({ margins: { ...doc.margins, o } })} />
      </Row>
      <Labeled label="Columns">
        <Row>
          <NumberField label="Columns" short="▥" value={doc.cols.n} min={1} max={24} places={0} onChange={(n) => set({ cols: { ...doc.cols, n } })} />
          <LengthField label="Column gutter" short="↔" units={u} value={doc.cols.g} min={0} max={288} onChange={(g) => set({ cols: { ...doc.cols, g } })} />
        </Row>
      </Labeled>
      <Labeled label="Baseline grid">
        <Row>
          <LengthField label="Baseline grid starts" short="⇣" units={u} value={doc.baseline.start} min={0}
            onChange={(start) => set({ baseline: { ...doc.baseline, start } })} />
          <LengthField label="Baseline every" short="≡" units={u} value={doc.baseline.step} min={1} max={144}
            onChange={(step) => set({ baseline: { ...doc.baseline, step } })} />
        </Row>
      </Labeled>
      <Row>
        <Labeled label="Grid every"><LengthField label="Document grid every" short="#" units={u} value={doc.grid.step} min={1} max={288}
          onChange={(step) => set({ grid: { step } })} /></Labeled>
        <Labeled label="Bleed"><LengthField label="Bleed" short="⤧" units={u} value={doc.bleed} min={0} max={72}
          onChange={(bleed) => set({ bleed })} /></Labeled>
      </Row>
      <Row>
        <Labeled label="Units"><Select label="Units" value={doc.units} options={UNITS} onChange={(units) => set({ units })} /></Labeled>
        <Labeled label="Paper"><ColorField label="Paper" value={doc.paper} onChange={(paper) => paper && set({ paper }, 'paper')} /></Labeled>
      </Row>
      {paid && doc.pages.length > 1 && (
        <Labeled label="Subscribers' pages start at page">
          <NumberField label="First page for subscribers" short="$" value={doc.paywall_page ?? 2} min={2} max={doc.pages.length} places={0}
            onChange={(n) => set({ paywall_page: n })} />
        </Labeled>
      )}
    </Section>
  )
}
