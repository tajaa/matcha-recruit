import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InventoryItem, SalesLine } from '../../api/inventory'
import SalesImportModal, { buildCommitLine, isLineValid, toDraftLine } from './SalesImportModal'

const mock = vi.hoisted(() => ({ getSalesImport: vi.fn(), commitSales: vi.fn() }))
vi.mock('../../api/inventory', () => ({ getSalesImport: mock.getSalesImport, commitSales: mock.commitSales }))

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

  it('does not throw when components arrives as an undecoded JSONB string', () => {
    // Regression: asyncpg has no jsonb codec registered, so a caller that
    // forgets to decode jsonb_agg(...) hands this component list back as a
    // raw JSON string, not an array — toDraftLine must not crash on it.
    const undecoded = { ...recipe, components: '[{"item_id":"cup","quantity_per_sale":1}]' as unknown as SalesLine['components'] }
    const draft = toDraftLine(undecoded)
    expect(draft.components).toEqual([{ item_id: '', quantity_per_sale: '1', unit: null }])
  })

  it('derives an explicit kind from the server mapping_kind, defaulting by component count', () => {
    expect(toDraftLine(recipe).kind).toBe('recipe')
    expect(toDraftLine({ ...recipe, components: [recipe.components![0]] }).kind).toBe('direct')
    expect(toDraftLine({ ...recipe, mapping_kind: 'direct' }).kind).toBe('direct')
  })

  it('rejects a direct-kind line with more than one component', () => {
    const draft = toDraftLine(recipe)
    draft.kind = 'direct'
    expect(isLineValid(draft)).toBe(false)
  })

  it('sends the line’s explicit kind, not a component-count guess', () => {
    const draft = toDraftLine(recipe)
    draft.mappingDirty = true
    draft.mapping_id = null
    draft.kind = 'direct'
    draft.components = [draft.components[0]]
    const payload = buildCommitLine(draft, 'loc-1')
    expect(payload.new_mapping?.kind).toBe('direct')
  })
})

describe('saved import store scope', () => {
  beforeEach(() => {
    mock.commitSales.mockResolvedValue({ unmapped: 0, items_affected: 1 })
  })

  it.each(['B', null])('uses the saved import store (%s) for stock choices and committed mappings', async (location) => {
    const user = userEvent.setup()
    mock.getSalesImport.mockResolvedValue({
      id: 'draft', location_id: location, business_date: '2026-10-16', source: 'email', filename: 'sales.csv',
      lines: [{ sold_name: 'Coffee', quantity: 1, status: 'unmapped', components: [] }],
    })
    const items = ['A', 'B', null].map((store) => ({
      id: store ?? 'shared', name: `${store ?? 'shared'} beans`, location_id: store, unit: 'kg',
    })) as InventoryItem[]
    render(<SalesImportModal open onClose={vi.fn()} items={items} locationId="A" draftImportId="draft" onCommitted={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'Stock item' }))
    expect(screen.queryByRole('button', { name: 'A beans' })).not.toBeInTheDocument()
    if (!location) expect(screen.queryByRole('button', { name: 'B beans' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'shared beans' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: `${location ?? 'shared'} beans` }))
    await user.click(screen.getByRole('button', { name: 'Commit sales' }))
    await waitFor(() => expect(mock.commitSales).toHaveBeenCalledWith(expect.objectContaining({
      import_id: 'draft', location_id: location ?? undefined,
      lines: [expect.objectContaining({ new_mapping: expect.objectContaining({ location_id: location }) })],
    })))
  })
})
