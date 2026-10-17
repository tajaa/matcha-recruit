import type { ComponentProps } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type SalesImportModal from '../components/inventory/SalesImportModal'
import type { InventoryItem, SalesImport, SalesMapping, SalesMappingInput } from '../api/inventory'

const mock = vi.hoisted(() => ({
  listItems: vi.fn(), listSalesImports: vi.fn(), listPOSConnections: vi.fn(),
  listSalesMappings: vi.fn(), upsertSalesMapping: vi.fn(), mapPOSItem: vi.fn(),
  mappings: [] as SalesMapping[],
}))

vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ hasFeature: (name: string) => name === 'sales_intake', me: null }) }))
vi.mock('../api/channels', () => ({ listChannelLocations: async () => [
  { id: 'A', name: 'Store A' }, { id: 'B', name: 'Store B' },
] }))
vi.mock('../api/inventory', () => ({
  listItems: mock.listItems, listSalesImports: mock.listSalesImports, listPOSConnections: mock.listPOSConnections,
  listSalesMappings: mock.listSalesMappings, upsertSalesMapping: mock.upsertSalesMapping, mapPOSItem: mock.mapPOSItem,
  listOrders: async () => ({ orders: [] }), listMovements: async () => ({ movements: [] }), listSuggestions: async () => ({}),
  listPOSLocations: async () => ({ locations: [] }),
  listPOSCatalog: async () => ({ items: [{ external_item_id: 'square-coffee', name: 'Square Coffee', sku: null }] }),
  listPOSMappings: async () => ({ mappings: [] }),
}))
vi.mock('../components/inventory/SalesImportModal', () => ({
  default: ({ open, draftImportId, locationId }: ComponentProps<typeof SalesImportModal>) => open
    ? <div data-testid="sales-modal">{draftImportId ?? 'upload'}:{locationId ?? 'company'}</div> : null,
}))
vi.mock('../components/inventory/InventoryHelp', () => ({
  default: () => null, InventoryHelpButton: () => null, InventoryHelpModal: () => null, INVENTORY_HELP: {},
}))
vi.mock('../components/inventory/ItemTable', () => ({ default: () => null }))
vi.mock('../components/inventory/ItemDetail', () => ({ default: () => null }))
vi.mock('../components/inventory/OrderQueue', () => ({ default: () => null }))
vi.mock('../components/inventory/ReceiveDeliveryModal', () => ({ default: () => null }))
vi.mock('../components/inventory/SalesIntakeWizard', () => ({ default: () => null }))
vi.mock('../components/inventory/InventoryWasteGuide', () => ({ default: () => null }))
vi.mock('../components/inventory/InventoryNavigation', () => ({ default: () => null }))

import InventoryHub from './InventoryHub'

function stock(id: string, location: string | null): InventoryItem {
  return {
    id, name: `${id} beans`, location_id: location, current_quantity: 10, unit: 'kg',
    low_stock_threshold: null, unit_cost: null, category: null, shelf_life_days: null, yield_pct: null,
    par_source: 'manual', auto_created: false, archived_at: null, location_name: null,
    created_at: '', updated_at: '', open_order: null,
  }
}

function draft(id: string, location: string | null): SalesImport {
  return { id, location_id: location, company_id: 'company', source: 'email', status: 'draft',
    business_date: '2026-10-16', filename: 'sales.csv', line_count: 1, mapped_count: 0, created_at: '' }
}

function renderHub(query = '?setup=sales&location=A') {
  render(<MemoryRouter initialEntries={[`/ops/inventory${query}`]}><InventoryHub /></MemoryRouter>)
  return screen.findByText('Inventory control center')
}

describe('inventory sales handoff', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    mock.listItems.mockResolvedValue({ items: [stock('item-A', 'A'), stock('item-B', 'B'), stock('shared', null)] })
    mock.listSalesImports.mockResolvedValue({ imports: [draft('draft-B', 'B'), draft('draft-A', 'A'), draft('draft-shared', null)] })
    mock.listPOSConnections.mockResolvedValue({ connections: [] })
    mock.mappings = []
    mock.listSalesMappings.mockImplementation(async (location?: string) => ({
      mappings: mock.mappings.filter((mapping) => !mapping.location_id || mapping.location_id === location),
    }))
    mock.upsertSalesMapping.mockImplementation(async (body: SalesMappingInput) => {
      const mapping = { ...body, id: 'mapping-A', normalized_name: 'a coffee', location_id: body.location_id ?? null,
        components: body.components.map((component) => ({ id: 'component', unit: null, ...component })) } as SalesMapping
      mock.mappings.push(mapping)
      return mapping
    })
  })

  it('counts and opens only the selected store drafts, even when another store has the newest', async () => {
    await renderHub()
    expect(screen.getByText(/1 sales import waiting for review/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review imports' }))
    expect(screen.getByTestId('sales-modal')).toHaveTextContent('draft-A:A')
  })

  it('opens an all-locations draft using that import’s actual store', async () => {
    await renderHub('')
    expect(screen.getByText(/3 sales imports waiting for review/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review imports' }))
    expect(screen.getByTestId('sales-modal')).toHaveTextContent('draft-B:B')
  })

  it('keeps unassigned draft review separate from store drafts', async () => {
    await renderHub('?location=none')
    expect(screen.getByText(/1 sales import waiting for review/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review imports' }))
    expect(screen.getByTestId('sales-modal')).toHaveTextContent('draft-shared:company')
  })

  it('refreshes Square choices when a store mapping is saved, and sends the selected mapping id', async () => {
    const user = userEvent.setup()
    mock.listPOSConnections.mockResolvedValue({ connections: [{ id: 'square', provider: 'square', status: 'connected' }] })
    await renderHub()
    await screen.findByText('Square Coffee')
    await user.type(screen.getByLabelText('Sold name'), 'A coffee')
    await user.click(screen.getByRole('button', { name: 'Stock item' }))
    expect(screen.queryByRole('button', { name: 'item-B beans' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'shared beans' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'item-A beans' }))
    await user.click(screen.getByRole('button', { name: 'Add mapping' }))
    await waitFor(() => expect(mock.upsertSalesMapping).toHaveBeenCalledWith(expect.objectContaining({ location_id: 'A' })))
    await user.click(await screen.findByRole('button', { name: 'Map to sales name…' }))
    await user.click(await screen.findByRole('button', { name: 'A coffee' }))
    await waitFor(() => expect(mock.mapPOSItem).toHaveBeenCalledWith('square', { external_item_id: 'square-coffee', mapping_id: 'mapping-A' }))
    expect(mock.listSalesMappings).toHaveBeenCalledWith('A')
  })

  it('does not offer another store draft when the selected store has none', async () => {
    mock.listSalesImports.mockResolvedValue({ imports: [draft('draft-B', 'B')] })
    await renderHub()
    expect(screen.queryByRole('button', { name: 'Review imports' })).not.toBeInTheDocument()
  })

  it('reloads Square mapping choices for a different selected store', async () => {
    mock.listPOSConnections.mockResolvedValue({ connections: [{ id: 'square', provider: 'square', status: 'connected' }] })
    await renderHub()
    await waitFor(() => expect(mock.listSalesMappings).toHaveBeenCalledWith('A'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Inventory location' }), { target: { value: 'B' } })
    await waitFor(() => expect(mock.listSalesMappings).toHaveBeenCalledWith('B'))
    fireEvent.click(screen.getByRole('button', { name: 'Review imports' }))
    expect(screen.getByTestId('sales-modal')).toHaveTextContent('draft-B:B')
  })
})
