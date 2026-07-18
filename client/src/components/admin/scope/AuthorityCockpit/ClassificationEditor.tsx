import { useState } from 'react'

import { api } from '../../../../api/client'
import { Button } from '../../../ui'
import type { AuthorityItem, Vocabulary } from './types'

/**
 * KEY / override editor — the step that had no UI at all.
 *
 * `PUT /items/{id}/classification` existed but was unwired, so an item Gemini
 * classified with a NULL regulation_key was permanently stalled: no key means
 * codify.py can never match it to a catalog row, and there was no way to supply
 * one short of curl. Same for a wrong disposition — the queue could only
 * rubber-stamp Gemini, never correct it.
 *
 * The override lands CONFIRMED (it is a human decision), and the server
 * re-validates against the same gates: an unknown category slug is rejected, an
 * unknown regulation_key is downgraded to NULL with a warning. That is why the
 * selects are populated from /vocabulary rather than free text — the operator
 * chooses from the vocabulary the server will actually accept.
 */
export function ClassificationEditor({
  item,
  vocab,
  onClose,
  onSaved,
}: {
  item: AuthorityItem
  vocab: Vocabulary
  onClose: () => void
  // keepOpen: the write landed but produced warnings the operator must read —
  // reload the queue, but don't dismiss the editor out from under them.
  onSaved: (opts?: { keepOpen?: boolean }) => void
}) {
  const [disposition, setDisposition] = useState(item.disposition ?? 'universal_in_domain')
  const [categorySlug, setCategorySlug] = useState<string>(() => {
    // Recover the RKD category that owns the item's current key, so the key
    // select opens on the right list instead of blank.
    const key = item.regulation_key
    if (!key) return ''
    return (
      Object.entries(vocab.keys_by_category).find(([, keys]) => keys.includes(key))?.[0] ?? ''
    )
  })
  const [regulationKey, setRegulationKey] = useState(item.regulation_key ?? '')
  const [appliesTo, setAppliesTo] = useState<string[]>(item.applies_to_categories ?? [])
  const [excludes, setExcludes] = useState<string[]>(item.excludes_categories ?? [])
  const [excludedReason, setExcludedReason] = useState(item.excluded_reason ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  const keyOptions = categorySlug ? (vocab.keys_by_category[categorySlug] ?? []) : []

  const toggle = (list: string[], set: (v: string[]) => void, slug: string) =>
    set(list.includes(slug) ? list.filter((s) => s !== slug) : [...list, slug])

  const save = async () => {
    setSaving(true)
    setError(null)
    setWarnings([])
    try {
      // Only send what the operator actually set — the endpoint is a PATCH over
      // model_fields_set, so an unsent jurisdiction_scope keeps its existing
      // value instead of silently widening to whole-index reach.
      // entity_condition is deliberately NOT sent: the route PATCH-preserves it
      // when unset. There is no trigger-authoring UI yet, and sending null would
      // wipe the condition — turning a conditional obligation universal.
      const body: Record<string, unknown> = {
        disposition,
        applies_to_categories: appliesTo,
        excludes_categories: excludes,
      }
      if (regulationKey) {
        body.regulation_key = regulationKey
        body.category_slug = categorySlug
      }
      if (disposition === 'excluded') body.excluded_reason = excludedReason
      const res = await api.put<{ warnings?: string[] }>(
        `/admin/scope-registry/items/${item.id}/classification`,
        body,
      )
      // The server's gates DOWNGRADE rather than reject: a regulation_key that
      // isn't in the RKD for that category is stored as NULL with a warning.
      // Swallowing that would be the worst possible outcome here — the operator
      // would believe they had keyed the item (the whole point of this editor)
      // while it stayed uncodifiable. Keep the editor open and say so.
      //
      // The write DID land, though (confirmed, key NULL), so the queue must
      // still reload — otherwise it keeps showing this row as unconfirmed and
      // the funnel counts are wrong until a manual refresh.
      if (res?.warnings?.length) {
        setWarnings(res.warnings)
        setRegulationKey('')
        onSaved({ keepOpen: true })
        return
      }
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const needsReason = disposition === 'excluded' && !excludedReason.trim()
  const needsApplies = disposition === 'category_specific' && appliesTo.length === 0

  return (
    <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[11px] text-zinc-200">{item.citation}</div>
          {item.heading && <div className="text-[11px] text-zinc-500">{item.heading}</div>}
        </div>
        <button onClick={onClose} className="text-[11px] text-zinc-500 hover:text-zinc-300">
          Cancel
        </button>
      </div>

      {error && <div className="mb-2 text-[11px] text-red-400">{error}</div>}
      {warnings.length > 0 && (
        <div className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1">
          {warnings.map((w) => (
            <div key={w} className="text-[11px] text-amber-300">{w}</div>
          ))}
          <div className="mt-0.5 text-[10px] text-amber-400/70">
            Saved, but NOT keyed — the item stays uncodifiable. Pick a key the RKD
            actually defines, or mint the key first.
          </div>
        </div>
      )}

      <div className="grid gap-2 md:grid-cols-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Disposition</span>
          <select
            value={disposition}
            onChange={(e) => setDisposition(e.target.value)}
            className="mt-0.5 w-full rounded border border-white/[0.08] bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200">
            {vocab.dispositions.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">
            Key category
          </span>
          <select
            value={categorySlug}
            onChange={(e) => {
              setCategorySlug(e.target.value)
              setRegulationKey('')  // the old key doesn't belong to the new category
            }}
            className="mt-0.5 w-full rounded border border-white/[0.08] bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200">
            <option value="">— none (uncodified) —</option>
            {Object.keys(vocab.keys_by_category).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">
            Regulation key
          </span>
          <select
            value={regulationKey}
            disabled={!categorySlug}
            onChange={(e) => setRegulationKey(e.target.value)}
            title={
              categorySlug
                ? 'Without a key this obligation can never be codified against the catalog.'
                : 'Pick a key category first.'
            }
            className="mt-0.5 w-full rounded border border-white/[0.08] bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200 disabled:opacity-40">
            <option value="">— none —</option>
            {keyOptions.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </label>
      </div>

      {disposition === 'excluded' ? (
        <label className="mt-2 block">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">
            Excluded reason (required)
          </span>
          <input
            value={excludedReason}
            onChange={(e) => setExcludedReason(e.target.value)}
            placeholder="e.g. construction-only standard; no general-industry application"
            className="mt-0.5 w-full rounded border border-white/[0.08] bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200"
          />
        </label>
      ) : (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {([
            ['Applies to', appliesTo, setAppliesTo,
             'Which business categories this obligation reaches. Required for category_specific.'],
            ['Excludes', excludes, setExcludes,
             'Categories this obligation explicitly does NOT reach, even if otherwise universal.'],
          ] as const).map(([label, list, set, hint]) => (
            <div key={label}>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500" title={hint}>
                {label}
              </span>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {vocab.categories.map((c) => (
                  <button
                    key={c.slug}
                    type="button"
                    onClick={() => toggle([...list], set as (v: string[]) => void, c.slug)}
                    className={`rounded border px-1.5 py-0.5 text-[10px] transition-colors ${
                      list.includes(c.slug)
                        ? 'border-sky-500/40 bg-sky-500/15 text-sky-300'
                        : 'border-white/[0.08] text-zinc-500 hover:border-white/20'
                    }`}>
                    {c.slug}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {item.entity_condition && (
        <div className="mt-2 rounded border border-white/[0.08] bg-white/[0.02] px-2 py-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">
            Trigger (kept as-is)
          </span>
          <div
            className="mt-0.5 font-mono text-[10px] text-zinc-400"
            title="This obligation only applies to facilities matching this condition. There is no trigger editor yet — saving preserves it rather than wiping it, which would make the obligation apply to everyone.">
            {JSON.stringify(item.entity_condition)}
          </div>
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={saving || needsReason || needsApplies}
          onClick={save}>
          {saving ? 'Saving…' : 'Save + confirm'}
        </Button>
        <span className="text-[10px] text-zinc-500">
          {needsReason
            ? 'An excluded classification needs a reason.'
            : needsApplies
              ? 'category_specific needs at least one applies-to category.'
              : 'Saving lands this CONFIRMED — the engine reads it immediately.'}
        </span>
      </div>
    </div>
  )
}
