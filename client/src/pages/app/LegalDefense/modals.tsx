import { useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { Button, Input, Modal, Select, Textarea, Toggle, useToast } from '../../../components/ui'
import { createMatter, sharePacket, type Matter, type MatterType, type Packet } from '../../../api/legalDefense'
import { MATTER_TYPES } from './shared'

export function NewMatterModal({ onClose, onCreated }: { onClose: () => void; onCreated: (m: Matter) => void }) {
  const [title, setTitle] = useState('')
  const [type, setType] = useState<MatterType>('class_action')
  const [allegation, setAllegation] = useState('')
  const [context, setContext] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [counsel, setCounsel] = useState(false)
  const [counselName, setCounselName] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (!title.trim()) { setErr('Give the matter a title.'); return }
    setSaving(true); setErr(null)
    try {
      const m = await createMatter({
        title: title.trim(), matter_type: type,
        allegation: allegation.trim() || null, defense_theory: context.trim() || null,
        evidence_start: start || null, evidence_end: end || null,
        counsel_directed: counsel, counsel_name: counsel ? (counselName.trim() || null) : null,
      })
      onCreated(m)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create matter')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="New legal matter">
      <div className="space-y-3">
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Doe v. Acme — class action" />
        <Select label="Type" value={type} options={MATTER_TYPES}
          onChange={(e) => setType(e.target.value as MatterType)} />
        <Textarea label="What's being alleged?" value={allegation} onChange={(e) => setAllegation(e.target.value)} rows={2}
          placeholder="The claim as you understand it." />
        <Textarea label="Factual context (optional)" value={context} onChange={(e) => setContext(e.target.value)} rows={2}
          placeholder="What you believe the records show. The assistant stays neutral — counsel draws conclusions." />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Evidence from" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input label="Evidence to" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2">
          <div>
            <div className="text-sm text-zinc-200">Prepared at the direction of counsel</div>
            <div className="text-[11px] text-zinc-500">Adds a work-product header to the packet.</div>
          </div>
          <Toggle checked={counsel} onChange={setCounsel} />
        </div>
        {counsel && (
          <Input label="Counsel name" value={counselName} onChange={(e) => setCounselName(e.target.value)} placeholder="Firm or attorney" />
        )}
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={saving}>{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create'}</Button>
        </div>
      </div>
    </Modal>
  )
}

export function ShareModal({ matterId, packet, onClose, toast }: {
  matterId: string; packet: Packet; onClose: () => void; toast: ReturnType<typeof useToast>['toast']
}) {
  const [email, setEmail] = useState('')
  const [days, setDays] = useState(14)
  const [link, setLink] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function create() {
    setBusy(true)
    try {
      const res = await sharePacket(matterId, packet.id, { recipient_email: email.trim() || undefined, expires_days: days })
      setLink(`${window.location.origin}${res.path}`)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to create link', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Send packet to counsel">
      <div className="space-y-3">
        <p className="text-sm text-zinc-400">
          Creates a private, expiring download link for your attorney — no Matcha login required.
        </p>
        <Input label="Recipient email (optional, for your records)" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="attorney@firm.example" />
        <Input label="Link expires in (days)" type="number" value={String(days)} onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 14))} />
        {link ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] p-3">
            <div className="text-[11px] uppercase tracking-wide text-emerald-400/80">Share link</div>
            <div className="mt-1 flex items-center gap-2">
              <code className="flex-1 truncate text-xs text-zinc-200">{link}</code>
              <Button size="sm" variant="secondary" onClick={() => { void navigator.clipboard.writeText(link); toast('Copied', 'success') }}>Copy</Button>
            </div>
          </div>
        ) : (
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}><X className="h-4 w-4" /> Close</Button>
            <Button onClick={() => void create()} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create link'}</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
