/**
 * The codification cockpit — drives the front half of the scope-registry
 * pipeline from the UI.
 *
 * INGEST → CLASSIFY → CONFIRM/KEY → RECONCILE was fully built on the backend
 * but had zero frontend callers: every one of these endpoints was curl-only,
 * and ScopeStudio's empty state told the operator to go run a Python script
 * (COMPLIANCE_SYSTEM_GAP_REVIEW.md §4). Classifications land 'provisional' and
 * every engine read filters `confirmed`, so with no confirm UI the registry
 * could never leave the empty state from inside the app.
 *
 * Nothing here is new backend surface — it's the existing 12 unwired routes.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../../../api/client'
import { Button, LABEL } from '../../ui'
import { HelpHint } from '../../ui/HelpHint'

type AuthorityIndex = {
  slug: string
  name: string
  level: string
  jurisdiction_id: string | null
  source_type: string
  enumerable: boolean
  item_count: number
  unclassified_count: number
  last_ingested_at: string | null
}

type AuthorityItem = {
  id: string
  citation: string
  heading: string | null
  disposition: string | null
  regulation_key: string | null
  status: string | null
  proposed_by: string | null
  applies_to_categories: string[] | null
  excludes_categories: string[] | null
  excluded_reason: string | null
}

type Vocabulary = {
  dispositions: string[]
  categories: Array<{ slug: string; label: string; parent: string | null }>
  keys_by_category: Record<string, string[]>
}

type Stratum = {
  id: string
  level: string
  jurisdiction_label: string | null
  category_slug: string | null
  label: string | null
  status: string
  item_count: number
  key_count: number
  refreshed_at: string | null
}

type ShadowRow = {
  id: string
  company_id: string | null
  company_name: string | null
  resolve_keys: string[]
  expand_keys: string[]
  only_in_resolve: string[]
  only_in_expand: string[]
  created_at: string
}

const DISPOSITION_BADGE: Record<string, string> = {
  universal_in_domain: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  category_specific: 'border-sky-500/30 bg-sky-500/15 text-sky-300',
  conditional: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  excluded: 'border-zinc-500/30 bg-zinc-500/15 text-zinc-400',
}

function pct(n: number, d: number): number {
  return d > 0 ? Math.round((100 * n) / d) : 0
}

/** Confirmed / provisional / unclassified for one index. */
function FunnelBar({ index }: { index: AuthorityIndex }) {
  const total = index.item_count || 0
  // unclassified_count means "no CONFIRMED classification" (classify.py), so
  // confirmed is the complement. Provisional work is inside `unclassified`.
  const confirmed = Math.max(0, total - (index.unclassified_count || 0))
  return (
    <div className="mt-1.5">
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${pct(confirmed, total)}%` }}
        />
      </div>
      <div className="mt-1 font-mono text-[10px] tabular-nums text-zinc-500">
        {confirmed}/{total} confirmed
        {index.unclassified_count > 0 && (
          <span className="ml-1 text-amber-400">· {index.unclassified_count} to review</span>
        )}
      </div>
    </div>
  )
}

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
function ClassificationEditor({
  item,
  vocab,
  onClose,
  onSaved,
}: {
  item: AuthorityItem
  vocab: Vocabulary
  onClose: () => void
  onSaved: () => void
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
      if (res?.warnings?.length) {
        setWarnings(res.warnings)
        setRegulationKey('')
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

export default function AuthorityCockpit({ onMutate }: { onMutate?: () => void }) {
  const [indexes, setIndexes] = useState<AuthorityIndex[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)

  const [openSlug, setOpenSlug] = useState<string | null>(null)
  const [items, setItems] = useState<AuthorityItem[] | null>(null)
  const [itemsError, setItemsError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<AuthorityItem | null>(null)
  const [vocab, setVocab] = useState<Vocabulary | null>(null)

  const [strata, setStrata] = useState<Stratum[] | null>(null)
  const [showStrata, setShowStrata] = useState(false)

  const [shadow, setShadow] = useState<ShadowRow[] | null>(null)
  const [showShadow, setShowShadow] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await api.get<{ indexes: AuthorityIndex[] }>('/admin/scope-registry/authority')
        if (!cancelled) { setIndexes(res.indexes); setError(null) }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load authority indexes')
      }
    })()
    return () => { cancelled = true }
  }, [nonce])

  // The vocabulary the server will actually accept (taxonomy slugs + RKD keys).
  // Fetched once — the editor can't exist without it.
  useEffect(() => {
    let cancelled = false
    api.get<Vocabulary>('/admin/scope-registry/vocabulary')
      .then((v) => { if (!cancelled) setVocab(v) })
      .catch(() => { /* editor stays disabled; the queue still works */ })
    return () => { cancelled = true }
  }, [])

  const refresh = useCallback(() => {
    setNonce((n) => n + 1)
    onMutate?.()
  }, [onMutate])

  const loadItems = useCallback(async (slug: string) => {
    setItemsError(null)
    setItems(null)
    setSelected(new Set())
    try {
      // confirmed=false, NOT classified=false: a Gemini-proposed classification
      // is still unconfirmed work, and every engine read filters
      // status='confirmed'. classified=false only shows items with no row at
      // all, which would hide exactly the provisional rows this queue drains.
      const res = await api.get<{ items: AuthorityItem[] }>(
        `/admin/scope-registry/authority/${encodeURIComponent(slug)}/items?confirmed=false`,
      )
      setItems(res.items)
    } catch (e) {
      setItemsError(e instanceof Error ? e.message : 'Failed to load items')
    }
  }, [])

  const act = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setBusy(label)
      setError(null)
      setNotice(null)
      try {
        const res = (await fn()) as { worker_online?: boolean; message?: string } | undefined
        // Ingest/Classify only .delay() onto Celery. With no worker listening the
        // POST still 200s and the task sits in Redis forever — so a bare "running"
        // is a lie, and the operator watches the counts never move. Say so.
        if (res && res.worker_online === false) {
          setNotice(res.message ?? 'Queued, but no Celery worker is running.')
        }
        refresh()
      } catch (e) {
        setError(e instanceof Error ? e.message : `${label} failed`)
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  const confirmSelected = useCallback(async () => {
    if (!selected.size || !openSlug) return
    await act('confirm', async () => {
      await api.post('/admin/scope-registry/classifications/confirm', {
        item_ids: [...selected],
      })
      await loadItems(openSlug)
    })
  }, [selected, openSlug, act, loadItems])

  const totals = useMemo(() => {
    const list = indexes ?? []
    return {
      indexes: list.length,
      items: list.reduce((a, i) => a + (i.item_count || 0), 0),
      unclassified: list.reduce((a, i) => a + (i.unclassified_count || 0), 0),
    }
  }, [indexes])

  return (
    <div className="mt-5 rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className={LABEL}>Codification cockpit</div>
          <HelpHint text="The authoring pipeline for the scope registry: ingest an authority's sections, classify them (Gemini proposes, you confirm), assign each obligation a registry key, then reconcile the confirmed keys against the catalog. Every engine read filters on CONFIRMED classifications — provisional work counts for nothing until you confirm it here." />
          {totals.unclassified > 0 && (
            <span className="rounded border border-amber-500/30 bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
              {totals.unclassified} to review
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setShowStrata((v) => !v)
              if (!strata) {
                api.get<{ strata: Stratum[] }>('/admin/scope-registry/strata')
                  .then((r) => setStrata(r.strata))
                  .catch(() => setStrata([]))
              }
            }}
            className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-400 hover:border-white/20">
            {showStrata ? 'Hide strata' : 'Strata'}
          </button>
          <button
            onClick={() => {
              setShowShadow((v) => !v)
              if (!shadow) {
                api.get<{ entries: ShadowRow[] }>('/admin/scope-registry/shadow-log')
                  .then((r) => setShadow(r.entries))
                  .catch(() => setShadow([]))
              }
            }}
            className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-400 hover:border-white/20">
            {showShadow ? 'Hide shadow log' : 'Shadow log'}
          </button>
          <Button size="sm"
            variant="secondary"
            disabled={busy !== null}
            onClick={() => act('reconcile', () => api.post('/admin/scope-registry/reconcile', {}))}>
            {busy === 'reconcile' ? 'Reconciling…' : 'Reconcile'}
          </Button>
        </div>
      </div>

      {error && <div className="mb-2 text-xs text-red-400">{error}</div>}
      {notice && (
        <div className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
          {notice}
        </div>
      )}

      {!indexes ? (
        <div className="text-xs text-zinc-500">Loading…</div>
      ) : indexes.length === 0 ? (
        <div className="text-xs text-amber-400">
          No authority indexes ingested yet. Ingest one below to start the registry — it is empty
          until then, and every engine surface falls back to the catalog.
        </div>
      ) : null}

      {/* Index list + funnel */}
      <div className="grid gap-2 md:grid-cols-2">
        {(indexes ?? []).map((ix) => (
          <div key={ix.slug} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm text-zinc-200">{ix.name}</div>
                <div className="mt-0.5 font-mono text-[10px] text-zinc-500">
                  {ix.slug} · {ix.level}
                  {!ix.enumerable && ' · curated'}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  disabled={busy !== null}
                  title="Re-read this authority's section list from the source. Two ingests are needed before drift can be detected."
                  onClick={() =>
                    act(`ingest:${ix.slug}`, () =>
                      api.post(`/admin/scope-registry/authority/${encodeURIComponent(ix.slug)}/ingest`, {}),
                    )
                  }
                  className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-zinc-400 hover:border-white/20 disabled:opacity-40">
                  {busy === `ingest:${ix.slug}` ? '…' : 'Ingest'}
                </button>
                <button
                  disabled={busy !== null}
                  title="Ask Gemini to propose a classification for every unclassified section. Proposals land PROVISIONAL — they do nothing until confirmed."
                  onClick={() =>
                    act(`classify:${ix.slug}`, () =>
                      api.post(`/admin/scope-registry/authority/${encodeURIComponent(ix.slug)}/classify`, {}),
                    )
                  }
                  className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-zinc-400 hover:border-white/20 disabled:opacity-40">
                  {busy === `classify:${ix.slug}` ? '…' : 'Classify'}
                </button>
                <button
                  disabled={busy !== null}
                  onClick={() => {
                    const next = openSlug === ix.slug ? null : ix.slug
                    setOpenSlug(next)
                    if (next) loadItems(next)
                  }}
                  className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-zinc-300 hover:border-white/20 disabled:opacity-40">
                  {openSlug === ix.slug ? 'Close' : 'Review'}
                </button>
              </div>
            </div>
            <FunnelBar index={ix} />
          </div>
        ))}
      </div>

      {/* Confirm / override queue for the open index */}
      {openSlug && (
        <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className={LABEL}>Unconfirmed · {openSlug}</span>
              <HelpHint text="Sections with no confirmed classification. Confirming one is what makes it real: resolve, codify, strata and the completeness denominator all read confirmed rows only." />
            </div>
            <Button size="sm"
              variant="primary"
              disabled={!selected.size || busy !== null}
              onClick={confirmSelected}>
              {busy === 'confirm' ? 'Confirming…' : `Confirm ${selected.size || ''}`.trim()}
            </Button>
          </div>

          {itemsError ? (
            <div className="text-xs text-red-400">{itemsError}</div>
          ) : !items ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : items.length === 0 ? (
            <div className="text-xs text-emerald-400">
              Nothing unconfirmed — every section in this index has a confirmed classification.
            </div>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-zinc-950 text-[10px] uppercase tracking-wider text-zinc-500">
                  <tr>
                    <th className="w-8 py-1">
                      <input
                        type="checkbox"
                        checked={items.length > 0 && selected.size === items.length}
                        onChange={(e) =>
                          setSelected(e.target.checked ? new Set(items.map((i) => i.id)) : new Set())
                        }
                      />
                    </th>
                    <th className="py-1">Citation</th>
                    <th className="py-1">Disposition</th>
                    <th className="py-1">Key</th>
                    <th className="py-1" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr key={it.id} className="border-t border-white/[0.04]">
                      <td className="py-1.5">
                        <input
                          type="checkbox"
                          checked={selected.has(it.id)}
                          onChange={(e) => {
                            const next = new Set(selected)
                            if (e.target.checked) next.add(it.id)
                            else next.delete(it.id)
                            setSelected(next)
                          }}
                        />
                      </td>
                      <td className="py-1.5">
                        <div className="font-mono text-[11px] text-zinc-300">{it.citation}</div>
                        {it.heading && (
                          <div className="truncate text-[11px] text-zinc-500">{it.heading}</div>
                        )}
                      </td>
                      <td className="py-1.5">
                        {it.disposition ? (
                          <>
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                DISPOSITION_BADGE[it.disposition] ?? DISPOSITION_BADGE.excluded
                              }`}>
                              {it.disposition}
                            </span>
                            {it.proposed_by && (
                              <span className="ml-1 text-[10px] text-zinc-600">
                                proposed by {it.proposed_by}
                              </span>
                            )}
                          </>
                        ) : (
                          <span
                            className="text-[11px] text-zinc-600"
                            title="No classification proposed yet — run Classify on this index first.">
                            unclassified
                          </span>
                        )}
                      </td>
                      <td className="py-1.5">
                        {it.regulation_key ? (
                          <span className="font-mono text-[10px] text-zinc-400">{it.regulation_key}</span>
                        ) : (
                          <span
                            className="text-[10px] text-amber-400"
                            title="No registry key: this obligation can never be codified against the catalog until one is assigned. Use Edit to assign one.">
                            no key
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 text-right">
                        <button
                          type="button"
                          disabled={!vocab}
                          onClick={() => setEditing(editing?.id === it.id ? null : it)}
                          title={
                            vocab
                              ? 'Assign a regulation key, or correct the disposition Gemini proposed. Saving lands it confirmed.'
                              : 'Vocabulary failed to load — reload the page.'
                          }
                          className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-zinc-400 hover:border-white/20 disabled:opacity-40">
                          {editing?.id === it.id ? 'Close' : it.regulation_key ? 'Edit' : 'Assign key'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {editing && vocab && (
            <ClassificationEditor
              item={editing}
              vocab={vocab}
              onClose={() => setEditing(null)}
              onSaved={() => {
                setEditing(null)
                if (openSlug) loadItems(openSlug)
                refresh()
              }}
            />
          )}
        </div>
      )}

      {/* Strata inspector */}
      {showStrata && (
        <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <div className={`${LABEL} mb-2`}>Strata</div>
          {!strata ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : strata.length === 0 ? (
            <div className="text-xs text-zinc-500">No strata materialized yet.</div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-[10px] uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="py-1">Level</th>
                  <th className="py-1">Jurisdiction</th>
                  <th className="py-1">Category</th>
                  <th className="py-1 text-right">Items</th>
                  <th className="py-1 text-right">Keys</th>
                </tr>
              </thead>
              <tbody>
                {strata.map((s) => (
                  <tr key={s.id} className="border-t border-white/[0.04] text-[11px]">
                    <td className="py-1 text-zinc-400">{s.level}</td>
                    <td className="py-1 text-zinc-300">{s.jurisdiction_label ?? '—'}</td>
                    <td className="py-1 font-mono text-zinc-400">{s.category_slug ?? '—'}</td>
                    <td className="py-1 text-right font-mono tabular-nums text-zinc-400">{s.item_count}</td>
                    <td className="py-1 text-right font-mono tabular-nums text-zinc-400">{s.key_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Shadow log — the cutover go/no-go signal */}
      {showShadow && (
        <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className={LABEL}>Shadow log</span>
            <HelpHint text="Every onboarding finalize runs the registry alongside the authoritative expand_scope path and records the diff. Agreement here is the evidence that justifies cutting a coordinate over to the engine (cutover.py's allowlist) — without this surface the shadow phase could never end." />
          </div>
          {!shadow ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : shadow.length === 0 ? (
            <div className="text-xs text-zinc-500">
              No shadow runs recorded yet — finalize an onboarding session to record one.
            </div>
          ) : (
            <>
              {(() => {
                const agreed = shadow.filter(
                  (r) => r.only_in_resolve.length === 0 && r.only_in_expand.length === 0,
                ).length
                return (
                  <div className="mb-2 font-mono text-[11px] tabular-nums text-zinc-400">
                    agreement {pct(agreed, shadow.length)}%{' '}
                    <span className="text-zinc-600">
                      ({agreed}/{shadow.length} runs with an identical key set)
                    </span>
                  </div>
                )
              })()}
              <table className="w-full text-left text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-zinc-500">
                  <tr>
                    <th className="py-1">When</th>
                    <th className="py-1">Company</th>
                    <th className="py-1 text-right">Engine</th>
                    <th className="py-1 text-right">Bank</th>
                    <th className="py-1 text-right">Engine only</th>
                    <th className="py-1 text-right">Bank only</th>
                  </tr>
                </thead>
                <tbody>
                  {shadow.slice(0, 20).map((r) => (
                    <tr key={r.id} className="border-t border-white/[0.04] text-[11px]">
                      <td className="py-1 text-zinc-400">
                        {new Date(r.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-1 truncate text-zinc-400">{r.company_name ?? '—'}</td>
                      <td className="py-1 text-right font-mono tabular-nums text-zinc-300">
                        {r.resolve_keys.length}
                      </td>
                      <td className="py-1 text-right font-mono tabular-nums text-zinc-300">
                        {r.expand_keys.length}
                      </td>
                      <td className="py-1 text-right font-mono tabular-nums text-emerald-400">
                        {r.only_in_resolve.length || '—'}
                      </td>
                      <td className="py-1 text-right font-mono tabular-nums text-amber-400">
                        {r.only_in_expand.length || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}
