import { AdminButton as Button, AdminInput as Input, AdminSelect as Select, AdminCard, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminActionMenu } from '../../../../components/admin/AdminActionMenu'
import { AdminTabs as PillTabs } from '../../../../components/admin/AdminTabs'
import { useEffect, useState } from 'react'
import { api } from '../../../../api/client'
import { graphicUrl } from '../../../../cappe/studio/model/graphics'
import { Modal, useToast } from '../../../../components/ui'
import type { CappeStudioBankItem } from '../../../../types/cappeAdmin'

type Kind = CappeStudioBankItem['kind']

const BASE = '/cappe/matcha-admin/studio-bank'
const LICENSES = [
  { value: 'gummfit', label: 'Gummfit (ours to give)' },
  { value: 'cc0', label: 'CC0' },
  { value: 'pdm', label: 'Public domain' },
  { value: 'by', label: 'CC BY (credit the creator)' },
  { value: 'by-sa', label: 'CC BY-SA (credit the creator)' },
] as const
const GROUPS = [
  { value: 'shapes', label: 'Shape' },
  { value: 'lines', label: 'Line or divider' },
  { value: 'badges', label: 'Badge or banner' },
  { value: 'icons', label: 'Icon' },
  { value: 'stickers', label: 'Sticker' },
  { value: 'patterns', label: 'Pattern' },
] as const
const COLOURS = [
  { value: 'auto', label: 'Work it out from the file' },
  { value: 'one', label: 'One colour: sites recolour it' },
  { value: 'own', label: 'Keeps its own colours' },
] as const

function preview(item: CappeStudioBankItem): string {
  if (item.kind === 'graphic') return item.sha ? graphicUrl(item.sha) : ''
  return item.variants?.webp?.[0]?.url || item.url || ''
}

// Adds a photo (re-encoded with its sizes, credited) or an SVG graphic
// (cleaned, stored by its sha) to the bank.
function AddForm({ kind, onAdded }: { kind: Kind; onAdded: (item: CappeStudioBankItem) => void }) {
  const { toast } = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [fileKey, setFileKey] = useState(0)
  const [name, setName] = useState('')
  const [tags, setTags] = useState('')
  const [collection, setCollection] = useState('')
  const [creator, setCreator] = useState('')
  const [credit, setCredit] = useState('')
  const [license, setLicense] = useState('gummfit')
  const [group, setGroup] = useState('shapes')
  const [colour, setColour] = useState('auto')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    form.append('name', name)
    form.append('tags', tags)
    form.append('collection', collection)
    if (kind === 'photo') {
      form.append('creator', creator)
      form.append('credit_line', credit)
      form.append('license', license)
    } else {
      form.append('group', group)
      form.append('colour', colour)
    }
    setBusy(true)
    try {
      const item = await api.upload<CappeStudioBankItem>(`${BASE}/${kind === 'photo' ? 'photos' : 'graphics'}`, form)
      onAdded(item)
      setFile(null)
      setFileKey((k) => k + 1)
      setName('')
      setTags('')
      setCredit('')
      toast(`${item.name} is in every site's Studio`, 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not add it', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AdminCard className="p-4">
      <p className="text-sm text-zinc-300">{kind === 'photo' ? 'Add a photo' : 'Add a graphic'}</p>
      <p className="mt-1 text-xs text-zinc-500">
        {kind === 'photo'
          ? 'Every site’s Studio shows it first under Photos → Gummfit. Placing it puts it in that site’s library, credited as you say here. Only add photos Gummfit may give out.'
          : 'An SVG, at most 200 KB. Scripts, styles and links are stripped. A one-colour graphic is a silhouette sites can recolour; a colourful one is kept as drawn. It shows first under Elements → From Gummfit.'}
      </p>
      <form onSubmit={submit} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Input key={fileKey} label={kind === 'photo' ? 'Photo (JPEG, PNG, WebP)' : 'SVG file'} type="file" required
          accept={kind === 'photo' ? 'image/jpeg,image/png,image/webp,image/gif' : '.svg,image/svg+xml'}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        <Input label="Name" required maxLength={120} placeholder={kind === 'photo' ? 'Harbour at dawn' : 'Wave divider'} value={name} onChange={(event) => setName(event.target.value)} />
        <Input label="Tags (comma-separated)" maxLength={500} placeholder="sea, boats, morning" value={tags} onChange={(event) => setTags(event.target.value)} />
        <Input label="Collection (optional)" maxLength={60} placeholder="Coast" value={collection} onChange={(event) => setCollection(event.target.value)} />
        {kind === 'photo' ? (
          <>
            <Input label="Creator" maxLength={200} placeholder="Who took it" value={creator} onChange={(event) => setCreator(event.target.value)} />
            <Select label="Licence" value={license} onChange={(event) => setLicense(event.target.value)} options={LICENSES} />
            <Input label="Credit line (optional)" maxLength={500} placeholder={creator ? `${creator} / Gummfit` : 'Gummfit'} value={credit} onChange={(event) => setCredit(event.target.value)} />
          </>
        ) : (
          <>
            <Select label="Kind of graphic" value={group} onChange={(event) => setGroup(event.target.value)} options={GROUPS} />
            <Select label="Colour" value={colour} onChange={(event) => setColour(event.target.value)} options={COLOURS} />
          </>
        )}
        <div className="sm:col-span-3">
          <Button type="submit" disabled={busy || !file || !name.trim()}>{busy ? 'Adding…' : 'Add to the bank'}</Button>
        </div>
      </form>
    </AdminCard>
  )
}

function EditModal({ item, onClose, onSaved }: { item: CappeStudioBankItem; onClose: () => void; onSaved: (item: CappeStudioBankItem) => void }) {
  const { toast } = useToast()
  const [name, setName] = useState(item.name)
  const [tags, setTags] = useState(item.tags.join(', '))
  const [collection, setCollection] = useState(item.collection ?? '')
  const [order, setOrder] = useState(String(item.sort_order))
  const [creator, setCreator] = useState(item.creator ?? '')
  const [credit, setCredit] = useState(item.credit_line ?? '')
  const [license, setLicense] = useState(item.license ?? 'gummfit')
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        name, tags: tags.split(','), collection, sort_order: Number(order) || 0,
      }
      if (item.kind === 'photo') Object.assign(body, { creator, credit_line: credit, license })
      onSaved(await api.patch<CappeStudioBankItem>(`${BASE}/${item.id}`, body))
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not save', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`Edit · ${item.name}`} width="sm">
      <div className="space-y-4">
        <Input label="Name" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
        <Input label="Tags (comma-separated)" maxLength={500} value={tags} onChange={(event) => setTags(event.target.value)} />
        <Input label="Collection" maxLength={60} value={collection} onChange={(event) => setCollection(event.target.value)} />
        <Input label="Order (lower shows first)" type="number" value={order} onChange={(event) => setOrder(event.target.value)} />
        {item.kind === 'photo' && (
          <>
            <Input label="Creator" maxLength={200} value={creator} onChange={(event) => setCreator(event.target.value)} />
            <Input label="Credit line (empty: creator / Gummfit)" maxLength={500} value={credit} onChange={(event) => setCredit(event.target.value)} />
            <Select label="Licence" value={license} onChange={(event) => setLicense(event.target.value as typeof license)} options={LICENSES} />
            <p className="text-xs text-zinc-500">Sites that already placed this photo keep the credit it had then.</p>
          </>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={saving || !name.trim()} onClick={save}>{saving ? 'Saving…' : 'Save'}</Button>
        </div>
      </div>
    </Modal>
  )
}

// Gummfit Studio's bank: the photos and graphics every site's Studio shows
// first. A photo can be deleted (sites keep the ones they placed); a graphic
// is hidden instead, because pages use it by name.
export default function CappeStudioBank() {
  const { toast } = useToast()
  const [kind, setKind] = useState<Kind>('photo')
  const [items, setItems] = useState<CappeStudioBankItem[] | null>(null)
  const [editing, setEditing] = useState<CappeStudioBankItem | null>(null)

  useEffect(() => {
    let alive = true
    api.get<CappeStudioBankItem[]>(`${BASE}?kind=${kind}`)
      .then((rows) => { if (alive) setItems(rows) })
      .catch((error) => { if (alive) { setItems([]); toast(error instanceof Error ? error.message : 'Could not load the bank', 'error') } })
    return () => { alive = false }
  }, [kind, toast])

  const replace = (item: CappeStudioBankItem) => setItems((prev) => (prev ?? []).map((i) => (i.id === item.id ? item : i)))

  async function setStatus(item: CappeStudioBankItem, status: CappeStudioBankItem['status']) {
    try {
      replace(await api.patch<CappeStudioBankItem>(`${BASE}/${item.id}`, { status }))
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not change it', 'error')
    }
  }

  async function remove(item: CappeStudioBankItem) {
    if (!window.confirm(`Take “${item.name}” out of the bank? Sites that placed it keep their copy.`)) return
    try {
      await api.delete(`${BASE}/${item.id}`)
      setItems((prev) => (prev ?? []).filter((i) => i.id !== item.id))
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not delete it', 'error')
    }
  }

  return (
    <div className="space-y-6">
      <PillTabs label="Kind" size="sm" value={kind} onChange={(next) => { setItems(null); setKind(next) }}
        options={[{ value: 'photo', label: 'Photos' }, { value: 'graphic', label: 'Graphics' }]} />
      <AddForm key={kind} kind={kind} onAdded={(item) => setItems((prev) => [item, ...(prev ?? [])])} />
      {items === null ? <p className="text-sm text-zinc-500">Loading…</p> : (
        <AdminTable className="min-w-[760px]">
          <thead>
            <tr><th className="w-20" /><th>Name</th><th>Collection</th><th>{kind === 'photo' ? 'Credit' : 'Kind'}</th><th>Status</th><th className="text-right">Actions</th></tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="align-top text-zinc-300">
                <td>
                  <img src={preview(item)} alt="" loading="lazy"
                    className={`h-12 w-16 rounded ${item.kind === 'photo' ? 'object-cover' : 'bg-zinc-100 object-contain p-1'}`} />
                </td>
                <td>
                  <p className="text-zinc-100">{item.name}</p>
                  {item.tags.length > 0 && <p className="mt-0.5 text-xs text-zinc-500">{item.tags.join(', ')}</p>}
                </td>
                <td className="text-zinc-400">{item.collection ?? '—'}</td>
                <td className="text-xs text-zinc-400">
                  {item.kind === 'photo' ? item.credit_line : `${GROUPS.find((g) => g.value === item.graphic_group)?.label ?? item.graphic_group}${item.mono ? ', one colour' : ''}`}
                </td>
                <td className={item.status === 'live' ? 'text-emerald-300' : 'text-zinc-500'}>{item.status === 'live' ? 'Live' : 'Hidden'}</td>
                <td className="text-right">
                  <AdminActionMenu label={`Actions for ${item.name}`} items={[
                    { label: 'Edit', onSelect: () => setEditing(item) },
                    item.status === 'live'
                      ? { label: 'Hide', onSelect: () => void setStatus(item, 'hidden') }
                      : { label: 'Show', onSelect: () => void setStatus(item, 'live') },
                    ...(item.kind === 'photo' ? [{ label: 'Delete', onSelect: () => void remove(item), danger: true }] : []),
                  ]} />
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="text-center text-zinc-500">Nothing in the bank yet.</td></tr>}
          </tbody>
        </AdminTable>
      )}
      {editing && <EditModal item={editing} onClose={() => setEditing(null)} onSaved={(item) => { replace(item); setEditing(null) }} />}
    </div>
  )
}
