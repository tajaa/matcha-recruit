import { api } from '../../api/client'

// ── Types ──

export type MovementKind = 'out' | 'in' | 'stockout' | 'adjust' | 'sale'
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
  unit_cost: number | null
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
  expected?: {
    expected: number | null
    baseline: number | null
    baseline_at: string | null
    received: number
    sold: number
    manual_out: number
    stockouts: number
  } | null
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
  unit_cost?: number
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
    unit_cost: number
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

// ── Stock audit ──

export interface AuditCommitLine {
  item_id?: string
  new_item_name?: string
  counted_quantity: number
}

export interface AuditCommitResult {
  total: number
  applied: number
  failed: number
  errors: { row: number; item: string; error: string }[]
  variance?: {
    run_id: string
    total_units: number
    total_value: number | null
    biggest_over: { item_id: string; name: string | null; units: number; value: number | null }[]
    biggest_short: { item_id: string; name: string | null; units: number; value: number | null }[]
  }
}

export function commitAudit(body: { location_id?: string | null; note?: string; lines: AuditCommitLine[] }) {
  return api.post<AuditCommitResult>('/inventory/audit/commit', body)
}

export interface AuditSheetRow {
  item: InventoryItem
  expected: number | null
  baseline: number | null
  baseline_at: string | null
  received: number
  sold: number
  manual_out: number
  stockouts: number
}

export function getAuditSheet(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<AuditSheetRow[]>(`/inventory/audit/sheet${qs}`)
}

export interface AuditRun {
  id: string
  company_id: string
  location_id: string | null
  committed_by: string | null
  committed_at: string
  note: string | null
  line_count: number
  variance_units: number | null
  variance_value: number | null
}

export function listAuditRuns() {
  return api.get<{ runs: AuditRun[] }>('/inventory/audit/runs')
}

export function getAuditRun(runId: string) {
  return api.get<AuditRun>(`/inventory/audit/runs/${runId}`)
}

// ── Sales intake ──

export interface SalesLine {
  item_name?: string
  sold_name: string
  quantity: number
  gross_sales: number | null
  business_date?: string | null
  mapping_id: string | null
  item_id: string | null
  quantity_per_sale?: number | null
  components?: { item_id: string; quantity_per_sale: number; unit?: string | null }[]
  status: 'mapped' | 'unmapped' | 'ignored'
  matched_name?: string | null
  auto_match?: { id: string; name: string } | null
}

export interface SalesDraft {
  business_date: string | null
  lines: SalesLine[]
  available: boolean
}

export interface SalesCommitResult {
  import_id: string
  total: number
  mapped: number
  unmapped: number
  items_affected: number
  errors: { row?: number; item?: string; error: string }[]
}

export function parseSales(file: File, locationId?: string) {
  const form = new FormData()
  form.append('file', file)
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.upload<SalesDraft>(`/inventory/sales/parse${qs}`, form)
}

export function commitSales(body: {
  location_id?: string | null
  business_date?: string | null
  source?: 'upload' | 'email'
  filename?: string | null
  gmail_message_id?: string | null
  force?: boolean
  lines: Omit<SalesLine, 'item_name' | 'matched_name' | 'auto_match'>[]
}) {
  return api.post<SalesCommitResult>('/inventory/sales/commit', body)
}

export function downloadSalesTemplate() {
  return api.download('/inventory/sales/template', 'inventory_sales_template.csv')
}

export interface SalesImport {
  id: string
  company_id: string
  location_id: string | null
  source: 'upload' | 'email'
  status: 'draft' | 'committed' | 'discarded'
  gmail_message_id?: string | null
  business_date: string | null
  filename: string | null
  line_count: number
  mapped_count: number
  created_at: string
}

export function listSalesImports(status?: SalesImport['status']) {
  const qs = status ? `?status=${status}` : ''
  return api.get<{ imports: SalesImport[] }>(`/inventory/sales/imports${qs}`)
}

export function getSalesImport(importId: string) {
  return api.get<SalesImport & { lines: SalesLine[]; raw?: { business_date?: string | null; lines?: SalesLine[] } | null }>(`/inventory/sales/imports/${importId}`)
}

export function discardSalesImport(importId: string) {
  return api.delete<{ id: string; status: string }>(`/inventory/sales/imports/${importId}`)
}

export interface SalesMapping {
  id: string
  sold_name: string
  normalized_name: string
  kind: 'direct' | 'recipe' | 'ignore'
  location_id: string | null
  components: { id: string; item_id: string; quantity_per_sale: number; unit: string | null }[]
}

export function listSalesMappings(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<{ mappings: SalesMapping[] }>(`/inventory/sales/mappings${qs}`)
}

export function upsertSalesMapping(body: {
  sold_name: string
  kind: SalesMapping['kind']
  location_id?: string | null
  components: { item_id: string; quantity_per_sale: number; unit?: string | null }[]
}) {
  return api.post<SalesMapping>('/inventory/sales/mappings', body)
}

export function deleteSalesMapping(mappingId: string) {
  return api.delete<{ id: string; deleted: boolean }>(`/inventory/sales/mappings/${mappingId}`)
}

export interface SalesSource {
  id: string
  company_id: string
  location_id: string | null
  from_address: string
  subject_match: string | null
  is_active: boolean
}

export function listSalesSources() {
  return api.get<{ sources: SalesSource[] }>('/inventory/sales/sources')
}

export function createSalesSource(body: { from_address: string; subject_match?: string | null; location_id?: string | null }) {
  return api.post<SalesSource>('/inventory/sales/sources', body)
}

export function deleteSalesSource(sourceId: string) {
  return api.delete<{ id: string; deleted: boolean }>(`/inventory/sales/sources/${sourceId}`)
}

export interface VoiceCountLine {
  item_name: string
  quantity: number
  unit: string | null
  item_id: string | null
  matched_name: string | null
  exact: boolean
}

export interface VoiceCountDraft {
  available: boolean
  transcript: string | null
  model: string | null
  lines: VoiceCountLine[]
}

export function parseAuditVoice(wav: Blob, locationId?: string) {
  const form = new FormData()
  form.append('file', wav, 'counts.wav')
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.upload<VoiceCountDraft>(`/inventory/audit/voice-parse${qs}`, form)
}
