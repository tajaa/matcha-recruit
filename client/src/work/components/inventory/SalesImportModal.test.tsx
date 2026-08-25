import { describe, expect, it } from 'vitest'
import type { SalesLine } from '../../api/inventory'
import { buildCommitLine, isLineValid, toDraftLine } from './SalesImportModal'

const recipe: SalesLine = {
  sold_name: 'Vanilla latte',
  quantity: 3,
  gross_sales: 18,
  mapping_id: 'mapping-latte',
  item_id: null,
  status: 'mapped',
  components: [
    { item_id: 'cup', quantity_per_sale: 1, unit: 'each' },
    { item_id: 'milk', quantity_per_sale: 0.25, unit: 'l' },
    { item_id: 'coffee', quantity_per_sale: 0.04, unit: 'kg' },
    { item_id: 'syrup', quantity_per_sale: 0.02, unit: 'l' },
  ],
}

describe('SalesImportModal mapping payloads', () => {
  it('preserves every component returned by a recipe mapping', () => {
    const draft = toDraftLine(recipe)
    expect(draft.components).toHaveLength(4)
    expect(draft.components.map((component) => component.item_id)).toEqual(['cup', 'milk', 'coffee', 'syrup'])
    expect(draft.components[1].quantity_per_sale).toBe('0.25')
  })

  it('keeps an unchanged recipe mapping by id while submitting every component', () => {
    const payload = buildCommitLine(toDraftLine(recipe), 'loc-1')
    expect(payload.mapping_id).toBe('mapping-latte')
    expect(payload.new_mapping).toBeUndefined()
    expect(payload.components).toHaveLength(4)
  })

  it('creates a reusable recipe when upload review changes its components', () => {
    const draft = toDraftLine(recipe)
    draft.mappingDirty = true
    draft.mapping_id = null
    draft.components[3].quantity_per_sale = '0.03'
    const payload = buildCommitLine(draft, 'loc-1')

    expect(payload.mapping_id).toBeNull()
    expect(payload.new_mapping).toEqual({
      sold_name: 'Vanilla latte',
      kind: 'recipe',
      location_id: 'loc-1',
      components: [
        { item_id: 'cup', quantity_per_sale: 1, unit: 'each' },
        { item_id: 'milk', quantity_per_sale: 0.25, unit: 'l' },
        { item_id: 'coffee', quantity_per_sale: 0.04, unit: 'kg' },
        { item_id: 'syrup', quantity_per_sale: 0.03, unit: 'l' },
      ],
    })
  })

  it('rejects duplicate, blank, and non-positive component rows', () => {
    const draft = toDraftLine(recipe)
    draft.components[1].item_id = 'cup'
    expect(isLineValid(draft)).toBe(false)
    draft.components[1].item_id = 'milk'
    draft.components[2].quantity_per_sale = '0'
    expect(isLineValid(draft)).toBe(false)
    draft.components[2].quantity_per_sale = ''
    expect(isLineValid(draft)).toBe(false)
  })
})
