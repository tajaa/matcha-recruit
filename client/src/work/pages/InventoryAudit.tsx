import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Mic, Sparkles, Square } from 'lucide-react'
import { ApiError } from '../../api/client'
import { Button, useToast } from '../../components/ui'
import { useMe } from '../../hooks/useMe'
import { useVoiceDictation } from '../../hooks/useVoiceDictation'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import {
  commitAudit, getAuditSheet, listItems, parseAuditVoice,
  type AuditCommitLine, type AuditSheetRow, type InventoryItem, type VoiceCountLine,
} from '../api/inventory'
import { listChannelLocations, type ChannelLocation } from '../api/channels'

function fmtElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

// Shared by touchedCount and handleSave so the Save button's count always
// matches what actually gets submitted. Blank/whitespace-only is
// "untouched", not zero.
function parseCountValue(raw: string): number | null {
  if (raw.trim() === '') return null
  const quantity = Number(raw)
  if (!Number.isFinite(quantity) || quantity < 0) return null
  return quantity
}

/** Bulk stock-count entry — a manager walks the store counting every item
 * and saves all the changed counts in one Save, instead of the one-item-
 * per-navigation `patchItem` flow on ItemDetail. Voice dictation (behind
 * `inventory_voice`) prefills the same edit map; it never writes on its
 * own — the manager still reviews and hits Save. */
export default function InventoryAudit() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { toast } = useToast()
  const { hasFeature } = useMe()
  const canDictate = hasFeature('inventory_voice')
  const canSales = hasFeature('sales_intake')

  const [items, setItems] = useState<InventoryItem[]>([])
  const [sheetRows, setSheetRows] = useState<AuditSheetRow[]>([])
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locFilter, setLocFilter] = useState<'all' | 'none' | string>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // itemId -> raw input text ("" means untouched/cleared, not "zero")
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [fromVoice, setFromVoice] = useState<Set<string>>(new Set())
  const [newLines, setNewLines] = useState<{ name: string; quantity: number }[]>([])

  const [transcribing, setTranscribing] = useState(false)
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null)
  const [unmatched, setUnmatched] = useState<VoiceCountLine[]>([])
  const [lastVariance, setLastVariance] = useState<NonNullable<Awaited<ReturnType<typeof commitAudit>>['variance']> | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    const request = canSales ? getAuditSheet().then((rows) => {
      setSheetRows(rows)
      setItems(rows.map((row) => row.item))
    }) : listItems().then((res) => {
      setSheetRows([])
      setItems(res.items)
    })
    request
      .catch(() => toast('Failed to load inventory', 'error'))
      .finally(() => setLoading(false))
  }, [canSales, toast])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    listChannelLocations().then(setLocations).catch(() => setLocations([]))
  }, [])

  const locationId = locFilter !== 'all' && locFilter !== 'none' ? locFilter : undefined

  const visibleItems = useMemo(() => {
    let list = items
    if (locFilter === 'none') list = list.filter((i) => !i.location_id)
    else if (locFilter !== 'all') list = list.filter((i) => i.location_id === locFilter)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter((i) => i.name.toLowerCase().includes(q))
    }
    return list
  }, [items, locFilter, search])

  const expectedById = useMemo(
    () => new Map(sheetRows.map((row) => [row.item.id, row])),
    [sheetRows],
  )

  const touchedCount = Object.values(edits).filter((v) => parseCountValue(v) !== null).length + newLines.length

  async function finishDictation() {
    const wav = await dictation.stop()
    if (!wav) { setVoiceMsg('No audio captured — try again.'); return }
    setTranscribing(true)
    setVoiceMsg(null)
    try {
      const draft = await parseAuditVoice(wav, locationId)
      if (!draft.available) {
        setVoiceMsg("Couldn't understand the audio — try again, or type the counts below.")
        return
      }
      const stillUnmatched = draft.lines.filter((line) => !line.item_id)
      setEdits((prev) => {
        const next = { ...prev }
        for (const line of draft.lines) {
          if (line.item_id) next[line.item_id] = String(line.quantity)
        }
        return next
      })
      setFromVoice((prev) => {
        const next = new Set(prev)
        for (const line of draft.lines) if (line.item_id) next.add(line.item_id)
        return next
      })
      if (stillUnmatched.length) setUnmatched((prev) => [...prev, ...stillUnmatched])
      if (!draft.lines.length) setVoiceMsg("Didn't catch any counts — try speaking closer to the mic.")
      // Dictated counts must be visible for review before Save — a search
      // term or a specific-store filter could otherwise hide a matched row.
      if (draft.lines.some((line) => line.item_id)) {
        setSearch('')
        setLocFilter('all')
      }
    } catch (err) {
      const tooMany = err instanceof ApiError && err.status === 429
      setVoiceMsg(tooMany
        ? 'Too many dictation attempts — wait a moment, or just type the counts.'
        : 'Transcription failed — please type the counts below.')
    } finally {
      setTranscribing(false)
    }
  }

  const dictation = useVoiceDictation({ maxDurationSeconds: 120, onMaxDuration: () => { void finishDictation() } })

  function acceptAsNew(line: VoiceCountLine) {
    setNewLines((prev) => [...prev, { name: line.item_name, quantity: line.quantity }])
    setUnmatched((prev) => prev.filter((l) => l !== line))
  }

  function dismissUnmatched(line: VoiceCountLine) {
    setUnmatched((prev) => prev.filter((l) => l !== line))
  }

  async function handleSave() {
    // `sources` mirrors `lines` 1:1 so a failed row (reported 1-indexed by
    // the backend) maps back to the edit/newLines entry that produced it —
    // needed to clear only what actually saved, not the whole sheet.
    const lines: AuditCommitLine[] = []
    const sources: ({ kind: 'edit'; itemId: string } | { kind: 'new'; index: number })[] = []
    for (const [itemId, raw] of Object.entries(edits)) {
      const quantity = parseCountValue(raw)
      if (quantity === null) continue
      lines.push({ item_id: itemId, counted_quantity: quantity })
      sources.push({ kind: 'edit', itemId })
    }
    newLines.forEach((line, index) => {
      lines.push({ new_item_name: line.name, counted_quantity: line.quantity })
      sources.push({ kind: 'new', index })
    })
    if (!lines.length) return

    setSaving(true)
    try {
      const result = await commitAudit({ location_id: locationId ?? null, lines })
      if (result.variance) setLastVariance(result.variance)
      const failedRows = new Set(result.errors.map((e) => e.row))
      const failedItemIds = new Set<string>()
      const failedNewIndexes = new Set<number>()
      sources.forEach((source, i) => {
        if (!failedRows.has(i + 1)) return
        if (source.kind === 'edit') failedItemIds.add(source.itemId)
        else failedNewIndexes.add(source.index)
      })

      if (result.failed > 0) {
        toast(`Saved ${result.applied} count${result.applied === 1 ? '' : 's'} — ${result.failed} failed, left for retry`, 'error')
      } else {
        toast(`Saved ${result.applied} count${result.applied === 1 ? '' : 's'}`, 'success')
      }
      // Only clear rows that actually committed — a failed row stays in the
      // sheet (still editable) instead of silently vanishing.
      setEdits((prev) => {
        const next: Record<string, string> = {}
        for (const [itemId, raw] of Object.entries(prev)) {
          if (failedItemIds.has(itemId)) next[itemId] = raw
        }
        return next
      })
      setFromVoice((prev) => {
        const next = new Set<string>()
        for (const id of prev) if (failedItemIds.has(id)) next.add(id)
        return next
      })
      setNewLines((prev) => prev.filter((_, index) => failedNewIndexes.has(index)))
      load()
    } catch {
      toast('Failed to save counts', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-5 p-6 pb-24">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">Inventory Audit</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Walk the store, enter what you count. Untouched items are left alone.</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => navigate(`${base}/inventory`)}
            className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
            Back to Inventory
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search items..."
          className="flex-1 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-1.5"
        />
        {locations.length > 0 && (
          <select
            value={locFilter}
            onChange={(e) => setLocFilter(e.target.value)}
            className="text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1.5"
          >
            <option value="all">All locations</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
            <option value="none">Unassigned</option>
          </select>
        )}
      </div>

      {canDictate && (
        <VoiceDictationBox
          dictation={dictation}
          transcribing={transcribing}
          voiceMsg={voiceMsg}
          finishDictation={finishDictation}
        />
      )}

      {unmatched.length > 0 && (
        <div className="space-y-1.5 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3">
          <p className="text-[12px] font-medium text-amber-300">Heard, but no matching item:</p>
          {unmatched.map((line, i) => (
            <div key={`${line.item_name}-${i}`} className="flex items-center justify-between gap-2 text-sm">
              <span className="text-zinc-300">"{line.item_name}" — {line.quantity}{line.unit ? ` ${line.unit}` : ''}</span>
              <span className="flex items-center gap-2">
                <button type="button" onClick={() => acceptAsNew(line)}
                  className="text-emerald-400 hover:underline text-[12px]">Add as new item</button>
                <button type="button" onClick={() => dismissUnmatched(line)}
                  className="text-zinc-500 hover:underline text-[12px]">Dismiss</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {newLines.length > 0 && (
        <div className="space-y-1 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] p-3">
          <p className="text-[12px] font-medium text-emerald-300">New items to add:</p>
          {newLines.map((line, i) => (
            <div key={`${line.name}-${i}`} className="flex items-center justify-between text-sm text-zinc-300">
              <span>{line.name} — {line.quantity}</span>
              <button type="button" onClick={() => setNewLines((prev) => prev.filter((_, idx) => idx !== i))}
                className="text-zinc-500 hover:underline text-[12px]">Remove</button>
            </div>
          ))}
        </div>
      )}

      {visibleItems.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No items match.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-900 text-left text-zinc-500 dark:text-zinc-400">
              <tr>
                <th className="px-4 py-2 font-medium">Item</th>
                <th className="px-4 py-2 font-medium">System count</th>
                {canSales && <th className="px-4 py-2 font-medium">Expected</th>}
                <th className="px-4 py-2 font-medium">Counted</th>
                {canSales && <th className="px-4 py-2 font-medium">Variance</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {visibleItems.map((item) => {
                const value = edits[item.id] ?? ''
                const touched = value !== ''
                const voiced = fromVoice.has(item.id)
                const sheetRow = expectedById.get(item.id)
                const expected = sheetRow?.expected ?? item.current_quantity
                const counted = parseCountValue(value)
                const variance = expected != null && counted != null ? counted - Number(expected) : null
                return (
                  <tr key={item.id} className={touched ? 'bg-emerald-500/5' : undefined}>
                    <td className="px-4 py-2">
                      <span className="text-zinc-900 dark:text-zinc-100">{item.name}</span>
                      {voiced && <Mic className="ml-1.5 inline h-3 w-3 text-emerald-500" />}
                    </td>
                    <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400">
                      {item.current_quantity ?? '?'}{item.unit ? ` ${item.unit}` : ''}
                    </td>
                    {canSales && <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400">
                      {expected ?? '?'}{item.unit ? ` ${item.unit}` : ''}
                    </td>}
                    <td className="px-4 py-2">
                      <input
                        inputMode="decimal"
                        value={value}
                        onChange={(e) => setEdits((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        placeholder={item.current_quantity != null ? String(item.current_quantity) : '—'}
                        className={`w-24 rounded-lg border px-2 py-1 text-right ${
                          touched
                            ? 'border-emerald-500/50 ring-1 ring-emerald-500/30'
                            : 'border-zinc-300 dark:border-zinc-700'
                        } bg-white dark:bg-zinc-900`}
                      />
                    </td>
                    {canSales && <td className={`px-4 py-2 text-right ${
                      variance == null ? 'text-zinc-500' : variance < 0 ? 'text-red-400' : variance > 0 ? 'text-emerald-400' : 'text-zinc-500'
                    }`}>
                      {variance == null ? '—' : `${variance > 0 ? '+' : ''}${variance}`}
                      {variance != null && item.unit_cost != null ? ` ($${(variance * Number(item.unit_cost)).toFixed(2)})` : ''}
                    </td>}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {canSales && lastVariance && (
        <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] p-4 text-sm">
          <p className="font-medium text-emerald-300">Audit variance saved</p>
          <p className="mt-1 text-zinc-300">Total units: {lastVariance.total_units}</p>
          {lastVariance.total_value != null && <p className="text-zinc-300">Total value: ${Number(lastVariance.total_value).toFixed(2)}</p>}
          {lastVariance.biggest_short[0] && <p className="mt-2 text-red-300">Biggest short: {lastVariance.biggest_short[0].name} ({lastVariance.biggest_short[0].units})</p>}
          {lastVariance.biggest_over[0] && <p className="text-emerald-300">Biggest over: {lastVariance.biggest_over[0].name} (+{lastVariance.biggest_over[0].units})</p>}
        </div>
      )}

      {touchedCount > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-10 border-t border-zinc-200 bg-white/95 px-6 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95">
          <div className="mx-auto flex max-w-4xl items-center justify-end gap-3">
            <button type="button" onClick={() => { setEdits({}); setNewLines([]); setFromVoice(new Set()) }}
              className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
              Cancel
            </button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : `Save ${touchedCount} count${touchedCount === 1 ? '' : 's'}`}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function VoiceDictationBox({ dictation, transcribing, voiceMsg, finishDictation }: {
  dictation: ReturnType<typeof useVoiceDictation>
  transcribing: boolean
  voiceMsg: string | null
  finishDictation: () => void | Promise<void>
}) {
  // Rendered by the caller regardless of the inventory_voice flag — the
  // caller only mounts this component at all when hasFeature is true; kept
  // as its own component so InventoryAudit's main body stays scannable.
  return (
    <div className="space-y-2">
      {dictation.status === 'recording' ? (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/40 bg-red-500/[0.07] px-4 py-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-500/20 text-red-300 animate-pulse">
            <Mic className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-zinc-100">Recording · {fmtElapsed(dictation.elapsedSeconds)}</div>
            <div className="text-[12px] text-red-300/80">Say each item and how many you counted.</div>
          </div>
          <button type="button" onClick={() => { void finishDictation() }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-400/50 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/15 transition-colors">
            <Square className="h-3.5 w-3.5 fill-current" /> Stop
          </button>
        </div>
      ) : transcribing ? (
        <div className="flex items-center gap-3 rounded-xl border border-white/[0.08] bg-zinc-800/40 px-4 py-3 text-sm text-zinc-300">
          <Loader2 className="h-4 w-4 animate-spin text-emerald-400" /> Transcribing counts…
        </div>
      ) : (
        <button type="button" onClick={() => { void dictation.start() }}
          className="group flex w-full items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] px-4 py-3 text-left transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/[0.1]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300 transition-colors group-hover:bg-emerald-500/25">
            <Mic className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-zinc-100">Dictate counts</span>
            <span className="block text-[12px] text-zinc-400">"Twelve boxes of gloves, six bags of espresso..." — you review before saving.</span>
          </span>
        </button>
      )}
      {dictation.status === 'denied' && <p className="px-0.5 text-[11px] text-amber-400">Microphone access denied — enable it in your browser settings, or type counts below.</p>}
      {dictation.status === 'error' && <p className="px-0.5 text-[11px] text-amber-400">Couldn't start recording — please type counts below.</p>}
      {voiceMsg && <p className="px-0.5 text-[11px] text-amber-400">{voiceMsg}</p>}
      <p className="px-0.5 text-[11px] text-zinc-500 flex items-center gap-1">
        <Sparkles className="h-3 w-3" /> AI-assisted — nothing saves until you hit Save below.
      </p>
    </div>
  )
}
