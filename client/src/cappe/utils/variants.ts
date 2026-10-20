// The product editor's variant table: one row per combination of the
// product's required pick-one groups (Size × Colour). The server is the
// authority (services/variants.py); this only lays the table out and builds
// the save request.
import type { CappeProduct, CappeProductVariantInput } from '../types'
import { parseMoneyCents } from './money'

export const MAX_VARIANTS = 100

type OptionLike = { id?: string; name: string }
type GroupLike = { name: string; select_type: 'single' | 'multi'; required: boolean; options: OptionLike[] }

export type ComboPart = { key: string; group: string; option: string }
export type VariantRow = {
  id?: string
  sku: string
  price: string
  stock: string
  image_url: string | null
  active: boolean
}

export const EMPTY_VARIANT: VariantRow = { sku: '', price: '', stock: '', image_url: null, active: true }

/** A stable key for an option row: its id once saved, else its place and name
 *  (a new option has no id until the save that creates it). */
export const optionKey = (groupIndex: number, option: OptionLike) =>
  option.id ?? `new:${groupIndex}:${option.name.trim()}`

/** One key per combination, whatever order its options are listed in. */
export const comboKey = (keys: string[]) => [...keys].sort().join('|')

/** The groups a variant is made of: required, pick-one, named, with options. */
export function isVariantGroup(group: GroupLike) {
  return group.select_type === 'single' && group.required && group.name.trim() !== ''
    && group.options.some((o) => o.name.trim())
}

/** Every combination of the variant groups, in group order. `tooMany` when
 *  there are more than the server keeps, so the editor can say so instead of
 *  drawing a table it can't save. */
export function combinations(groups: GroupLike[]): { combos: ComboPart[][]; tooMany: boolean } {
  const axes = groups
    .map((g, gi) => ({ g, gi }))
    .filter(({ g }) => isVariantGroup(g))
    .map(({ g, gi }) => g.options.filter((o) => o.name.trim())
      .map((o) => ({ key: optionKey(gi, o), group: g.name.trim(), option: o.name.trim() })))
  if (!axes.length) return { combos: [], tooMany: false }
  const count = axes.reduce((n, a) => n * a.length, 1)
  if (count > MAX_VARIANTS) return { combos: [], tooMany: true }
  let combos: ComboPart[][] = [[]]
  for (const axis of axes) combos = combos.flatMap((c) => axis.map((part) => [...c, part]))
  return { combos, tooMany: false }
}

/** The editor's rows for a saved product, keyed by combination. Saved options
 *  are keyed by id, which is what a variant stores. */
export function rowsFromProduct(product: CappeProduct): Record<string, VariantRow> {
  const out: Record<string, VariantRow> = {}
  for (const v of product.variants || []) {
    out[comboKey(v.option_ids)] = {
      id: v.id,
      sku: v.sku || '',
      price: v.price_cents == null ? '' : String(v.price_cents / 100),
      stock: v.inventory == null ? '' : String(v.inventory),
      image_url: v.image_url,
      active: v.status === 'active',
    }
  }
  return out
}

/** The `variants` list for the save request, or an error to show. Stock is
 *  sent only when the save changes it, with the count the form was showing,
 *  exactly like product and option stock. */
export function variantPayload(
  combos: ComboPart[][], rows: Record<string, VariantRow>, was: CappeProduct | null,
): { variants: CappeProductVariantInput[] } | { error: string } {
  const shelf = new Map((was?.variants || []).map((v) => [v.id, v.inventory ?? null]))
  const variants: CappeProductVariantInput[] = []
  for (const combo of combos) {
    const row = rows[comboKey(combo.map((p) => p.key))] || EMPTY_VARIANT
    const label = combo.map((p) => p.option).join(' / ')
    const price = row.price.trim() === '' ? null : parseMoneyCents(row.price)
    if (row.price.trim() !== '' && price === null) {
      return { error: `${label} — enter the price as a plain amount, e.g. 29 or 29.99` }
    }
    const raw = row.stock.trim()
    const next = raw === '' ? null : Number(raw)
    if (next !== null && (!Number.isInteger(next) || next < 0)) {
      return { error: `${label} — stock is a whole number, 0 or more (blank = not tracked)` }
    }
    const known = row.id !== undefined && shelf.has(row.id)
    const before = known ? shelf.get(row.id as string) ?? null : null
    const stockChange = known
      ? (next === before ? {} : { inventory: next, expected_inventory: before })
      : (next === null ? {} : { inventory: next })
    variants.push({
      ...(row.id ? { id: row.id } : {}),
      options: combo.map((p) => ({ group: p.group, option: p.option })),
      sku: row.sku.trim() || null,
      price_cents: price,
      image_url: row.image_url,
      status: row.active ? 'active' : 'disabled',
      ...stockChange,
    })
  }
  return { variants }
}

/** "M / Red" for a saved variant. */
export function variantName(product: CappeProduct, optionIds: string[]): string {
  const wanted = new Set(optionIds)
  return product.option_groups
    .flatMap((g) => g.options.filter((o) => wanted.has(o.id)).map((o) => o.name))
    .join(' / ') || 'a removed combination'
}
