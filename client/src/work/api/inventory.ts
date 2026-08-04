import { api } from '../../api/client'

// ── Types ──

export type MovementKind = 'out' | 'in' | 'stockout' | 'adjust'
export type OrderStatus = 'queued' | 'ordered' | 'received' | 'cancelled'

export interface InventoryOrder {
  id: string
  item_id: string
  status: OrderStatus
  suggested_quantity: number | null
  quantity: number | null
  suggestion: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface InventoryItem {
  id: string
  name: string
  unit: string | null
  current_quantity: number | null
  low_stock_threshold: number | null
  auto_created: boolean
  archived_at: string | null
  location_id: string | null
  location_name: string | null
  created_at: string
  updated_at: string
  open_order: InventoryOrder | null
}

export interface InventoryMovement {
  id: string
  item_id: string
  kind: MovementKind
  quantity: number | null
  quantity_delta: number | null
  quantity_estimated: boolean
  note: string | null
  narrative: string
  created_at: string
}

export interface ItemListResponse {
  items: InventoryItem[]
}

export interface ItemDetailResponse {
  item: InventoryItem
  movements: InventoryMovement[]
}

export interface MovementListResponse {
  movements: InventoryMovement[]
}

export interface OrderListResponse {
  orders: InventoryOrder[]
}

export interface InventorySuggestion {
  name: string
  suggested_quantity: number | null
  daily_rate: number | null
  avg_stockout_interval_days: number | null
  cover_days: number
  confidence: 'high' | 'medium' | 'low'
  n_samples: number
}

// ── Items ──

export async function listItems(includeArchived = false) {
  return api.get<ItemListResponse>(`/inventory/items?include_archived=${includeArchived}`)
}

export async function createItem(body: {
  name: string
  unit?: string
  current_quantity?: number
  low_stock_threshold?: number
  location_id?: string
}) {
  return api.post<InventoryItem>('/inventory/items', body)
}

export async function getItem(itemId: string) {
  return api.get<ItemDetailResponse>(`/inventory/items/${itemId}`)
}

export async function patchItem(
  itemId: string,
  body: Partial<{
    name: string
    unit: string
    low_stock_threshold: number
    set_quantity: number
    archived: boolean
  }>,
) {
  return api.patch<InventoryItem>(`/inventory/items/${itemId}`, body)
}

// ── Movements ──

export async function listMovements(params: { itemId?: string; limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams()
  if (params.itemId) qs.set('item_id', params.itemId)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  return api.get<MovementListResponse>(`/inventory/movements?${qs}`)
}

// ── Orders ──

export async function listOrders(status?: OrderStatus) {
  const qs = status ? `?status=${status}` : ''
  return api.get<OrderListResponse>(`/inventory/orders${qs}`)
}

export async function createOrder(body: { item_id: string; quantity?: number }) {
  return api.post<InventoryOrder>('/inventory/orders', body)
}

export async function approveOrder(orderId: string, quantity?: number) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/approve`, { quantity })
}

export async function receiveOrder(orderId: string, quantity?: number) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/receive`, { quantity })
}

export async function cancelOrder(orderId: string) {
  return api.post<InventoryOrder>(`/inventory/orders/${orderId}/cancel`, {})
}

// ── Receipts (invoice / packing-slip ingest) ──

export interface ReceiptLine {
  item_name: string
  quantity: number | null
  unit: string | null
  pack_size: string | null
  vendor_sku: string | null
  unit_price: number | null
  item_id: string | null
  matched_name: string | null
  exact: boolean
  open_order_id: string | null
}

export interface ReceiptDraft {
  vendor: string | null
  invoice_number: string | null
  invoice_date: string | null
  lines: ReceiptLine[]
  notes: string | null
  available: boolean
}

export interface ReceiptCommitResult {
  total_rows: number
  created: number
  failed: number
  errors: { row: number; item: string; error: string }[]
  ids: string[]
}

export function parseReceipt(file: File, locationId?: string) {
  const form = new FormData()
  form.append('file', file)
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.upload<ReceiptDraft>(`/inventory/receipts/parse${qs}`, form)
}

export function commitReceipt(body: {
  location_id?: string | null
  vendor?: string | null
  invoice_number?: string | null
  force?: boolean
  lines: { item_id?: string | null; new_item_name?: string | null; quantity: number; order_id?: string | null }[]
}) {
  return api.post<ReceiptCommitResult>('/inventory/receipts/commit', body)
}

export function downloadReceiptTemplate() {
  return api.download('/inventory/receipts/template', 'inventory_receipt_template.csv')
}

export async function listSuggestions() {
  return api.get<Record<string, InventorySuggestion>>('/inventory/suggestions')
}
