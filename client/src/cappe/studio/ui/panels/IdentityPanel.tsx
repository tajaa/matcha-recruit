import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import FontField from '../../../magazine/workspace/FontField'
import { CUTS } from '../../fonts/cuts'
import { ColorField, NumberField, Row, Section, Select } from '../../../magazine/workspace/controls'
import { allIds, charOf, newId } from '../../model/doc'
import { captureParent, detachParent, importIdentity, linkRole, removeStyle, removeSwatch, starterIdentity, IDENTITY_LIMITS } from '../../model/identity'
import { updateItems } from '../../model/ops'
import type { CharAttrs, Doc, MagazineIdentity, ParaAttrs } from '../../model/types'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'
import { Labeled } from '../fields'
import { identityLibrary, useIdentityLibrary } from '../identityLibrary'
import { currentType, hasTypeTarget, setChar, setPara } from '../typeTarget'

const button = 'rounded border border-zinc-700 px-2 py-1.5 text-[11px] text-zinc-200 hover:border-emerald-500 disabled:opacity-40'
const input = 'w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100'

/** A reusable magazine system, alongside the page's local formatting. */
export function IdentityPanel() {
  const c = useCtx(), s = useStudio(c.store, (s) => s), identity = s.doc.identity
  const library = identityLibrary(c.store, c.siteId), saved = useIdentityLibrary(c.store, c.siteId)
  const [tab, setTab] = useState<'paragraphs' | 'characters' | 'swatches' | 'parents'>('paragraphs')
  const [selected, select] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [parentName, setParentName] = useState('')
  useEffect(() => { void library.load() }, [library])
  const edit = (fn: (d: Doc) => Doc) => {
    setError(null)
    try {
      c.store.edit(fn); c.store.seal()
      void c.fonts.ensureDoc(c.store.get().doc).then(() => c.store.recompose(), (e) => setError(e instanceof Error ? e.message : 'Some fonts could not load.'))
    } catch (e) { setError(e instanceof Error ? e.message : 'The identity couldn’t be changed.') }
  }
  const change = (fn: (i: MagazineIdentity) => MagazineIdentity) => edit((d) => ({ ...d, identity: fn(d.identity ?? starterIdentity()) }))
  const chooseTab = (t: typeof tab) => { setTab(t); select(''); setError(null) }
  const applyStyle = (id: string) => {
    if (tab === 'paragraphs') setPara(c, { style: id }); else setChar(c, { style: id })
    void c.fonts.ensureDoc(c.store.get().doc).then(() => c.store.recompose(), () => c.store.set({ notice: 'Some style fonts could not load. Reopen the Studio to retry.' }))
  }
  const applyColour = (id: string) => {
    if (hasTypeTarget(s)) setChar(c, { swatch: id })
    const shapes = s.doc.items.filter((i) => s.selection.includes(i.id) && i.kind !== 'text' && (i.kind !== 'graphic' || i.color !== null))
    if (shapes.length) edit((d) => updateItems(d, shapes.map((i) => i.id), (i) => i.kind === 'line' ? { ...i, stroke_swatch: id } : { ...i, fill_swatch: id }))
  }
  const nameField = (name: string, onChange: (value: string) => void) => <Labeled label="Name">
      <input aria-label="Design name" className={input} maxLength={80} value={name}
        onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }} />
      </Labeled>
  const updateStyle = (patch: { name?: string; char?: CharAttrs; para?: ParaAttrs }) => change((i) => ({ ...i, [tab]: (tab === 'paragraphs' ? i.paragraphs : i.characters).map((r) => r.id === selected ? { ...r, ...patch } : r) }))
  const style = identity && (tab === 'paragraphs' ? identity.paragraphs : identity.characters).find((r) => r.id === selected)
  const paragraph = tab === 'paragraphs' ? identity?.paragraphs.find((r) => r.id === selected) : undefined
  const swatch = identity?.swatches.find((r) => r.id === selected)
  const addStyle = () => {
    const type = currentType(c, s), kind = tab === 'characters' ? 'characters' : 'paragraphs'
    const rows = identity![kind], id = newId(kind === 'characters' ? 'cs' : 'ps', rows.map((r) => r.id))
    let n = rows.length + 1; while (rows.some((r) => r.name === `Style ${n}`)) n++
    change((i) => ({ ...i, [kind]: [...i[kind], { id, name: `Style ${n}`, char: type.char, ...(kind === 'paragraphs' ? { para: type.para } : {}) }] }))
    select(id)
  }
  const capture = (id?: string) => {
    const name = parentName.trim()
    if (!name) { setError('Give the parent a name.'); return }
    edit((d) => captureParent(d, s.page, id ?? newId('pl', d.identity?.parents.map((p) => p.id) ?? allIds(d)), name))
  }
  return <Section title="Magazine identity">
    <p className="text-[11px] leading-relaxed text-zinc-400">Named styles, shared colours and recurring pages. Edit a style once to update its linked text throughout these pages.</p>
    {(error || saved.error) && <p role="alert" className="text-xs text-red-300">{error || saved.error}</p>}
    {saved.message && <p role="status" className="text-[11px] text-emerald-300">{saved.message}</p>}
    <div className="flex flex-wrap gap-2">
      {!identity && <button className={button}
        onClick={() => edit((d) => ({ ...d, identity: starterIdentity() }))}>Create identity</button>}
      {saved.identity && <button className={button} disabled={saved.loading || saved.pending}
        onClick={() => edit((d) => importIdentity(d, saved.identity!))}>Use saved magazine identity</button>}
      <button className={button} disabled={!identity || !saved.ready || saved.loading || saved.pending}
        onClick={() => identity && void library.save(identity)}>{saved.pending ? 'Saving identity…' : 'Save for this magazine'}</button>
      <button className={button} disabled={saved.pending || saved.loading}
        onClick={() => void library.load(true)}>Reload saved identity</button>
    </div>
    {identity && <>
      <Labeled label="Identity name">
      <input className={input} aria-label="Identity name" maxLength={80} value={identity.name}
        onChange={(e) => change((i) => ({ ...i, name: e.target.value }))} />
      </Labeled>
      <div className="grid grid-cols-2 gap-1" aria-label="Identity sections">{(['paragraphs', 'characters', 'swatches', 'parents'] as const).map((t) => <button key={t} aria-pressed={tab === t} className={`${button} ${tab === t ? 'bg-zinc-800 text-emerald-300' : ''}`}
        onClick={() => chooseTab(t)}>{({ paragraphs: 'Paragraph styles', characters: 'Character styles', swatches: 'Palette', parents: 'Parent layouts' })[t]}</button>)}</div>
      {(tab === 'paragraphs' || tab === 'characters') && <>
        <div className="space-y-1">{identity[tab].map((r) => <div className="flex gap-1" key={r.id}>
          <button className={`${button} flex-1 text-left ${selected === r.id ? 'border-emerald-500' : ''}`}
        onClick={() => select(r.id)}>{r.name || 'Unnamed style'}</button>
          <button className={button} disabled={!hasTypeTarget(s)}
        onClick={() => applyStyle(r.id)}>Apply</button>
        </div>)}</div>
        <button className={`${button} flex items-center gap-1`} disabled={identity[tab].length >= IDENTITY_LIMITS.styles}
        onClick={addStyle}>
      <Plus className="h-3 w-3" />Style from selection</button>
        {style && <div className="space-y-3 rounded border border-zinc-700 p-2">
          {nameField(style.name, (name) => updateStyle({ name }))}
          <StyleFields value={style.char} identity={identity}
        onChange={(char) => updateStyle({ char })} />
          {paragraph && <>
            <Select label="Alignment" value={paragraph.para.align ?? 'l'}
        options={[{ key: 'l', label: 'Left' }, { key: 'c', label: 'Centre' }, { key: 'r', label: 'Right' }, { key: 'j', label: 'Justify' }, { key: 'ja', label: 'Justify all lines' }]}
        onChange={(align) => updateStyle({ para: { ...paragraph.para, align } })} />
            <Row>
      <NumberField label="Leading" value={paragraph.para.lead ?? 0} min={0} max={2000}
        onChange={(lead) => updateStyle({ para: { ...paragraph.para, lead } })} />
      <NumberField label="Space before" value={paragraph.para.sb ?? 0} min={0} max={1000}
        onChange={(sb) => updateStyle({ para: { ...paragraph.para, sb } })} />
      </Row>
            <Row>
      <NumberField label="Space after" value={paragraph.para.sa ?? 0} min={0} max={1000}
        onChange={(sa) => updateStyle({ para: { ...paragraph.para, sa } })} />
      <NumberField label="First line indent" value={paragraph.para.fi ?? 0} min={-(paragraph.para.li ?? 0)} max={1000}
        onChange={(fi) => updateStyle({ para: { ...paragraph.para, fi } })} />
      </Row>
            <Row>
      <NumberField label="Left indent" value={paragraph.para.li ?? 0} min={0} max={1000}
        onChange={(li) => updateStyle({ para: { ...paragraph.para, li } })} />
      <NumberField label="Right indent" value={paragraph.para.ri ?? 0} min={0} max={1000}
        onChange={(ri) => updateStyle({ para: { ...paragraph.para, ri } })} />
      </Row>
            <Select label="Paragraph role" value={paragraph.para.role ?? 'p'}
        options={[{ key: 'p', label: 'Body' }, { key: 'h1', label: 'Headline' }, { key: 'h2', label: 'Heading' }, { key: 'h3', label: 'Subheading' }, { key: 'caption', label: 'Caption' }, { key: 'quote', label: 'Quote' }]}
        onChange={(role) => updateStyle({ para: { ...paragraph.para, role } })} />
            <button className={button}
        onClick={() => edit((d) => linkRole(d, paragraph.id))}>Link all {paragraph.para.role === 'p' ? 'body' : paragraph.para.role ?? 'body'} paragraphs</button>
          </>}
          <button className={`${button} flex items-center gap-1`}
        onClick={() => { edit((d) => removeStyle(d, tab === 'paragraphs' ? 'paragraphs' : 'characters', style.id)); select('') }}>
      <Trash2 className="h-3 w-3" />Delete style, keep appearance</button>
        </div>}
      </>}
      {tab === 'swatches' && <>
        <div className="space-y-1">{identity.swatches.map((r) => <div key={r.id} className="flex gap-1">
      <button className={`${button} flex flex-1 items-center gap-2 text-left`}
        onClick={() => select(r.id)}>
      <span className="h-3 w-3 rounded-sm" style={{ background: r.color }} />{r.name}</button>
          <button className={button} disabled={!hasTypeTarget(s) && !s.doc.items.some((i) => s.selection.includes(i.id) && (i.kind !== 'graphic' || i.color !== null))}
        onClick={() => applyColour(r.id)}>Apply colour</button>
      </div>)}</div>
        <button className={button} disabled={identity.swatches.length >= IDENTITY_LIMITS.swatches}
        onClick={() => { const id = newId('sw', identity.swatches.map((s) => s.id)); change((i) => ({ ...i, swatches: [...i.swatches, { id, name: `Colour ${id.slice(2)}`, color: '#b44d35' }] })); select(id) }}>Add colour</button>
        {swatch && <>{nameField(swatch.name, (name) => change((i) => ({ ...i, swatches: i.swatches.map((r) => r.id === swatch.id ? { ...r, name } : r) })))}<ColorField label="Swatch colour" value={swatch.color}
        onChange={(color) => color && change((i) => ({ ...i, swatches: i.swatches.map((r) => r.id === swatch.id ? { ...r, color } : r) }))} />
      <button className={button}
        onClick={() => { edit((d) => removeSwatch(d, swatch.id)); select('') }}>Delete colour, keep appearance</button>
      </>}
      </>}
      {tab === 'parents' && <>
        <Select label="Parent for this page" value={s.doc.pages[s.page].parent ?? ''}
        options={[{ key: '', label: 'None' }, ...identity.parents.map((p) => ({ key: p.id, label: p.name }))]}
        onChange={(parent) => edit((d) => ({ ...d, pages: d.pages.map((p, k) => k === s.page ? { ...p, parent: parent || undefined } : p) }))} />
        <button className={button} disabled={!s.doc.pages[s.page].parent}
        onClick={() => edit((d) => detachParent(d, s.page))}>Detach parent to edit this page</button>
        <input aria-label="Parent name" className={input} maxLength={80} placeholder="Parent name" value={parentName}
        onChange={(e) => setParentName(e.target.value)} />
        <button className={button}
        onClick={() => capture()}>Save local page as new parent</button>
        <p className="text-[10px] text-zinc-500">Saving moves this page’s local frames into the parent. Detach to customize a page; update the parent to change every linked page.</p>
        {identity.parents.map((p) => <div key={p.id} className="space-y-1 rounded border border-zinc-800 p-2">
      <p className="text-xs">{p.name}</p>
      <div className="flex gap-1">
      <button className={button}
        onClick={() => { setParentName(p.name); edit((d) => captureParent(d, s.page, p.id, p.name)) }}>Update from local page</button>
      <button className={button}
        onClick={() => edit((d) => { let next = d; for (let k = 0; k < d.pages.length; k++) if (next.pages[k].parent === p.id) next = detachParent(next, k); return { ...next, identity: { ...next.identity!, parents: next.identity!.parents.filter((r) => r.id !== p.id) } } })}>Delete, keep pages</button>
      </div>
      </div>)}
      </>}
      <div className="space-y-3 border-t border-zinc-700 pt-3">
        <h4 className="text-xs text-zinc-300">Page numbers & running headers</h4>
        <label className="flex gap-2 text-[11px]">
      <input type="checkbox" checked={identity.furniture.numbers}
        onChange={(e) => change((i) => ({ ...i, furniture: { ...i.furniture, numbers: e.target.checked } }))} />Automatic page numbers</label>
        <input className={input} aria-label="Running header" placeholder="Running header" maxLength={120} value={identity.furniture.header}
        onChange={(e) => change((i) => ({ ...i, furniture: { ...i.furniture, header: e.target.value } }))} />
        <Row>
      <NumberField label="Start numbering at" value={identity.furniture.start} min={1} max={9999} places={0}
        onChange={(start) => change((i) => ({ ...i, furniture: { ...i.furniture, start } }))} />
      <NumberField label="Edge inset" value={identity.furniture.inset} min={0} max={288}
        onChange={(inset) => change((i) => ({ ...i, furniture: { ...i.furniture, inset } }))} />
      </Row>
        <label className="flex gap-2 text-[11px]">
      <input type="checkbox" checked={identity.furniture.skip_first}
        onChange={(e) => change((i) => ({ ...i, furniture: { ...i.furniture, skip_first: e.target.checked } }))} />Skip the first page</label>
        <StyleFields value={identity.furniture.char} identity={identity}
        onChange={(char) => change((i) => ({ ...i, furniture: { ...i.furniture, char } }))} />
        <label className="flex gap-2 text-[11px]">
      <input type="checkbox" checked={!!s.doc.pages[s.page].hide_furniture}
        onChange={(e) => edit((d) => ({ ...d, pages: d.pages.map((p, k) => k === s.page ? { ...p, hide_furniture: e.target.checked } : p) }))} />Hide numbers & header on this page</label>
        <input className={input} aria-label="This page’s header" placeholder="This page’s header (blank uses magazine header)" maxLength={120} value={s.doc.pages[s.page].header ?? ''}
        onChange={(e) => edit((d) => ({ ...d, pages: d.pages.map((p, k) => k === s.page ? { ...p, header: e.target.value || undefined } : p) }))} />
      </div>
    </>}
  </Section>
}

function StyleFields({ value, identity, onChange }: { value: CharAttrs; identity: MagazineIdentity; onChange: (value: CharAttrs) => void }) {
  const full = charOf(value)
  return <div className="space-y-3">
    <FontField value={full.font} roles={false} cuts={CUTS}
        onChange={(font) => onChange({ ...value, font })} />
    <Row>
      <NumberField label="Style size" value={full.size} min={1} max={1296} step={0.5}
        onChange={(size) => onChange({ ...value, size })} />
      <NumberField label="Style weight" value={full.wt} min={100} max={900} step={100} places={0}
        onChange={(wt) => onChange({ ...value, wt })} />
      </Row>
    <label className="flex gap-2 text-[11px]">
      <input type="checkbox" checked={full.it}
        onChange={(e) => onChange({ ...value, it: e.target.checked })} />Italic</label>
    <label className="flex gap-2 text-[11px]">
      <input type="checkbox" checked={full.u}
        onChange={(e) => onChange({ ...value, u: e.target.checked })} />Underline</label>
    <NumberField label="Style tracking" value={full.track} min={-500} max={2000} places={0}
        onChange={(track) => onChange({ ...value, track })} />
    <Select label="Style palette colour" value={value.swatch ?? ''}
        options={[{ key: '', label: 'Custom colour' }, ...identity.swatches.map((s) => ({ key: s.id, label: s.name }))]}
        onChange={(swatch) => onChange({ ...value, swatch: swatch || undefined })} />
    {!value.swatch && <ColorField label="Style colour" value={full.color}
        onChange={(color) => color && onChange({ ...value, color })} />}
  </div>
}
