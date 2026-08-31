import { api } from '../../api/client'
import type { InventoryNetworkPlan } from '../types'

// ── Types ──

export type MovementKind = 'out' | 'in' | 'stockout' | 'adjust' | 'sale' | 'waste'
export type WasteReason =
  | 'spoilage' | 'expired' | 'prep_error' | 'overproduction'
  | 'breakage' | 'contamination' | 'theft' | 'comp' | 'recall' | 'unknown'
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
  category: string | null
  shelf_life_days: number | null
  yield_pct: number | null
  par_source: 'manual' | 'auto'
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
  waste_reason: WasteReason | null
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
  category?: string
  shelf_life_days?: number
  yield_pct?: number
  par_source?: 'manual' | 'auto'
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
    category: string
    shelf_life_days: number
    yield_pct: number
    par_source: 'manual' | 'auto'
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
  received_on?: string | null
  force?: boolean
  lines: { item_id?: string | null; new_item_name?: string | null; quantity: number; order_id?: string | null; expires_on?: string | null; vendor_sku?: string | null; unit_price?: number | null; pack_size?: string | null }[]
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
  components?: SalesMappingComponentInput[]
  new_mapping?: SalesMappingInput | null
  status: 'mapped' | 'unmapped' | 'ignored'
  matched_name?: string | null
  auto_match?: { id: string; name: string } | null
  mapping_kind?: 'direct' | 'recipe' | 'ignore' | null
}

export type SalesMappingComponentInput = {
  item_id: string
  quantity_per_sale: number
  unit?: string | null
}

export type SalesMappingInput = {
  sold_name: string
  kind: 'direct' | 'recipe' | 'ignore'
  location_id?: string | null
  components: SalesMappingComponentInput[]
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
  import_id?: string | null
  location_id?: string | null
  business_date?: string | null
  source?: 'upload' | 'email' | 'square' | 'toast'
  filename?: string | null
  gmail_message_id?: string | null
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
  source: 'upload' | 'email' | 'square' | 'toast'
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
  components: ({ id: string } & Required<SalesMappingComponentInput>)[]
}

export function listSalesMappings(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<{ mappings: SalesMapping[] }>(`/inventory/sales/mappings${qs}`)
}

export function upsertSalesMapping(body: SalesMappingInput) {
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

// ── POS connections ──

export type POSConnection = {
  id: string
  provider: 'square' | 'toast'
  status: 'connected' | 'error' | 'disconnected'
  environment: string | null
  last_sync_at: string | null
  last_error: string | null
  updated_at: string
  has_credentials: boolean
}

export function listPOSConnections() {
  return api.get<{ connections: POSConnection[] }>('/inventory/sales/connections')
}

export function authorizeSquare() {
  return api.get<{ oauth_url: string }>('/inventory/sales/connections/authorize')
}

export function listPOSLocations(connectionId: string) {
  return api.get<{ locations: { external_location_id: string; name: string; timezone: string; status?: string; location_id: string | null }[] }>(`/inventory/sales/connections/${connectionId}/locations`)
}

export function listPOSCatalog(connectionId: string) {
  return api.get<{ items: { external_item_id: string; name: string; sku: string | null }[] }>(`/inventory/sales/connections/${connectionId}/catalog`)
}

export function bindPOSLocation(connectionId: string, body: { external_location_id: string; name: string; timezone: string; location_id: string }) {
  return api.put(`/inventory/sales/connections/${connectionId}/locations`, body)
}

export function mapPOSItem(connectionId: string, body: { external_item_id: string; mapping_id: string }) {
  return api.put(`/inventory/sales/connections/${connectionId}/mappings`, body)
}

export function listPOSMappings(connectionId: string) {
  return api.get<{ mappings: { external_item_id: string; mapping_id: string; sold_name: string }[] }>(`/inventory/sales/connections/${connectionId}/mappings`)
}

export function syncPOSConnection(connectionId: string, body: { start_date: string; end_date: string }) {
  return api.post<POSSyncResult>(`/inventory/sales/connections/${connectionId}/sync`, body)
}

export type POSSyncResult = {
  sync_run_id: string
  days_seen: number
  imports_created: number
  drafts_created: number
  unmapped_lines: number
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

// ── Forecasting ──

export type ForecastStatus = 'ready' | 'count_required' | 'no_demand' | 'insufficient_history'

export type ForecastSettings = {
  id?: string
  company_id?: string
  location_id: string | null
  horizon_days: number
  history_days: number
  default_lead_time_days: number
  default_safety_stock_days: number
  timezone: string
  par_auto_apply: boolean
  par_max_drift_pct: number
  configured: boolean
  created_at?: string
  updated_at?: string
}

export type ForecastOverride = {
  week_start: string
  demand_multiplier: number
  reason: string
  source?: 'manual' | 'ai_accepted'
  confidence?: 'low' | 'medium' | 'high' | null
}

export type ForecastAIDraft = {
  available: boolean
  model: string
  adjustments: ForecastOverride[]
  risks: string[]
  data_gaps: string[]
}

export type ForecastLine = {
  id?: string
  run_id: string
  item_id: string
  name: string
  unit: string | null
  location_id: string | null
  current_quantity: number | null
  unit_cost: number | null
  status: ForecastStatus
  confidence: 'low' | 'medium' | 'high'
  history_nonzero_days: number
  on_order_quantity: number
  projected_demand: number
  average_daily_demand: number
  lead_demand: number
  safety_demand: number
  target_quantity: number
  recommended_par: number | null
  par_basis: 'demand' | 'shelf_life' | 'structural_deficit' | 'no_demand' | 'insufficient'
  current_par: number | null
  shelf_cap_quantity: number | null
  shelf_cap: number | null
  shelf_life_capped: boolean
  suggested_quantity: number | null
  runout_date: string | null
  order_by_date: string | null
  daily_demand?: (number | string)[]
}

export type ForecastRun = {
  id: string
  company_id: string
  location_id: string | null
  forecast_start: string
  forecast_end: string
  history_start: string
  settings_snapshot: Record<string, unknown>
  override_count: number
  created_at: string
  lines: ForecastLine[]
  plan: ForecastReorderPlan
}

export type ForecastPlanLine = {
  item_id: string; name: string; unit: string | null; suggested_quantity: number | null
  average_daily_demand: number; lead_demand: number; runout_date: string | null
  order_by_date: string | null; days_until_order_by: number | null
  urgency: 'overdue' | 'within_7_days' | 'within_14_days' | 'later'; extended_cost: number | null
}
export type ForecastReorderPlan = { total_order_value: number | null; uncosted_count: number; buckets: Record<'overdue' | 'within_7_days' | 'within_14_days' | 'later', number>; suppressed_count: number; suppressed_by_status: Record<string, number>; lines: ForecastPlanLine[] }

type ForecastRequest = {
  location_id?: string | null
  forecast_start?: string
  overrides?: ForecastOverride[]
}

export function getForecastSettings(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<ForecastSettings>(`/inventory/forecast/settings${qs}`)
}

export function putForecastSettings(body: Omit<ForecastSettings, 'id' | 'company_id' | 'configured' | 'created_at' | 'updated_at'>) {
  return api.put<ForecastSettings>('/inventory/forecast/settings', body)
}

export function listForecastRules(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<{ rules: Record<string, unknown>[] }>(`/inventory/forecast/replenishment-rules${qs}`)
}

export function previewForecast(body: ForecastRequest) {
  return api.post<{
    forecast_start: string
    forecast_end: string
    history_start: string
    settings: ForecastSettings
    overrides: ForecastOverride[]
    lines: ForecastLine[]
  }>('/inventory/forecast/preview', body)
}

export function createForecastRun(body: ForecastRequest) {
  return api.post<ForecastRun>('/inventory/forecast/runs', body)
}

export function draftForecastAdjustments(body: { location_id?: string | null; horizon_start?: string; manager_context: string }) {
  return api.post<ForecastAIDraft>('/inventory/forecast/ai-draft', body)
}

export function getLatestForecastRun(locationId?: string) {
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.get<ForecastRun | null>(`/inventory/forecast/runs/latest${qs}`)
}

export function getForecastRun(runId: string) {
  return api.get<ForecastRun>(`/inventory/forecast/runs/${runId}`)
}

export function getInventoryNetworkPlan(runId: string) {
  return api.get<InventoryNetworkPlan>(`/inventory/forecast/network?run_id=${encodeURIComponent(runId)}`)
}

export function applyForecastPar(runId: string, body: { item_ids?: string[]; mode?: 'manual' | 'huume' } = {}) {
  return api.post<{ considered: number; applied: number; skipped: { item_id: string; reason: string }[] }>(`/inventory/forecast/runs/${runId}/apply-par`, body)
}
export type ForecastParPreview = { considered: number; would_apply: number; would_skip: number; max_drift_pct: number; blocked_by_reason: Record<string, number>; proposals: { item_id: string; name: string; current_par: number | null; recommended_par: number | null; par_basis: string; drift_pct: number | null; allowed: boolean; reason: string; overridable: boolean; already_applied: boolean }[] }
export function previewForecastPar(runId: string, body: { item_ids?: string[]; mode?: 'manual' | 'huume' } = {}) { return api.post<ForecastParPreview>(`/inventory/forecast/runs/${runId}/par-preview`, body) }
export type InventoryInsight = { headline: string; detail: string; diagnosis: string; action: 'right_size_par' | 'review_handling' | 'check_rotation' | 'count_stock' | 'none'; confidence: string }
export function getForecastInsight(runId: string) { return api.post<InventoryInsight>(`/inventory/forecast/insight?run_id=${runId}`, {}) }

export type InventorySupplier = { id: string; name: string; contact_email: string | null; contact_phone: string | null; payment_terms: string | null; active: boolean }
export type BuyingAlternative = { supplier_id: string; supplier_name: string; purchase_quantity: number; expected_arrival: string | null; landed_cost: number | null; eligible: boolean; reason: string }
export type BuyingLine = {
  id: string | null; item_id: string; item_name: string; unit: string | null; location_id: string | null; location_name: string | null
  action: 'count_first' | 'hold' | 'buy' | 'expedite'; needed_quantity: number | null; transfer_quantity: number; purchase_quantity: number | null
  supplier_id: string | null; supplier_item_id: string | null; supplier_name: string | null; order_by_date: string | null
  expected_arrival: string | null; projected_runout: string | null; landed_cost: number | null; confidence: 'low' | 'medium' | 'high'
  price_confirmation_required: boolean; rationale: string; alternatives: BuyingAlternative[]
}
export type BuyingPlan = {
  id: string | null; forecast_run_id: string; location_id: string | null; input_fingerprint: string; created_at: string | null
  summary: { count_first: number; hold: number; buy: number; expedite: number; total_landed_cost: number | null; unpriced_count: number }
  lines: BuyingLine[]
}

export function listInventorySuppliers() { return api.get<{ suppliers: InventorySupplier[] }>('/inventory/buying/suppliers') }
export function createInventorySupplier(body: { name: string; contact_email?: string; contact_phone?: string; payment_terms?: string }) { return api.post<InventorySupplier>('/inventory/buying/suppliers', body) }
export function putInventorySupplierItem(itemId: string, body: { supplier_id: string; location_id?: string | null; vendor_sku?: string; purchase_unit?: string; pack_size_label?: string; units_per_pack: number; minimum_order_quantity: number; unit_price?: number; freight_flat?: number; lead_time_days?: number; price_observed_on?: string; preferred?: boolean; active?: boolean }) { return api.put(`/inventory/buying/supplier-items/${itemId}`, body) }
export function createBuyingRun(body: { forecast_run_id: string; location_id?: string | null }) { return api.post<BuyingPlan>('/inventory/buying/runs', body) }
export function stageBuyingLine(lineId: string) { return api.post<{ order_id: string; status: string }>(`/inventory/buying/lines/${lineId}/stage`, {}) }
export function downloadBuyingPlan(forecastRunId: string, locationId?: string) {
  const params = new URLSearchParams({ forecast_run_id: forecastRunId })
  if (locationId) params.set('location_id', locationId)
  return api.download(`/inventory/buying/export.csv?${params.toString()}`, 'inventory-buying-plan.csv')
}

export type WasteRollup = { total_units: number; total_value: number | null; revenue: number | null; waste_pct_of_revenue: number | null; groups: { key: string; label: string; units: number; value: number | null; pct: number | null }[] }
export function getWasteRollup(start: string, end: string, groupBy: 'reason' | 'category' | 'item' = 'reason', locationId?: string) {
  return api.get<WasteRollup>(`/inventory/waste/rollup?start=${start}&end=${end}&group_by=${groupBy}${locationId ? `&location_id=${locationId}` : ''}`)
}
export type WasteSummary = { current: WasteRollup; prior: WasteRollup; value_delta: number | null; value_pct_change: number | null; comparable: boolean; direction: 'up' | 'down' | 'flat' | 'unknown'; bleeder: WasteRollup['groups'][number] | null; dominant_reason: string | null; diagnosis: 'over_ordering' | 'handling' | 'unexplained_shrink' | 'external' | 'mixed'; bleeder_reason_mix: WasteRollup['groups'] }
export type WasteRiskLine = { item_id: string; name: string; unit: string | null; item_current_quantity: number | null; open_lot_quantity: number; soonest_days_to_expiry: number; average_daily_demand: number; demand_basis: 'ledger' | 'insufficient_history'; confidence: string; n_samples: number; quantity_at_risk: number; value_at_risk: number | null; uncosted_count: number; lot_drift: number | null }
export function getWasteSummary(start: string, end: string, locationId?: string) { return api.get<WasteSummary>(`/inventory/waste/summary?start=${start}&end=${end}${locationId ? `&location_id=${locationId}` : ''}`) }
export function getWasteAtRisk(locationId?: string, withinDays = 14) {
  const params = new URLSearchParams({ within_days: String(withinDays) })
  if (locationId) params.set('location_id', locationId)
  return api.get<{ lines: WasteRiskLine[] }>(`/inventory/waste/at-risk?${params.toString()}`)
}
export function getWasteInsight(body: { start: string; end: string; location_id?: string }) { return api.post<InventoryInsight>('/inventory/waste/insight', body) }
export function recordWaste(body: { item_id: string; quantity: number; reason: WasteReason; note?: string }) {
  return api.post('/inventory/waste', body)
}
export function listExpiringLots(days = 7) { return api.get<{ lots: { id: string; item_id: string; name: string; quantity_remaining: number; expires_on: string; days_to_expiry: number }[] }>(`/inventory/waste/lots?expiring_within_days=${days}`) }
export function enrollAutoPar(itemIds: string[], enrolled: boolean) { return api.post('/inventory/waste/par/enroll', { item_ids: itemIds, enrolled }) }
export type ParHistoryEntry = { id: string; item_id: string; previous_par: number | null; new_par: number; par_basis: string | null; drift_pct: number | null; source: 'auto' | 'manual' | 'huume'; changed_at: string }
export function getParHistory(itemId: string) { return api.get<{ history: ParHistoryEntry[] }>(`/inventory/waste/par/history?item_id=${itemId}`) }
export type WasteAnalystCitation = { id: string; kind: string; data: unknown }
export function askWasteAnalyst(question: string) { return api.post<{ answer: string; citations: WasteAnalystCitation[] }>('/inventory/waste/ask', { question }) }
export function getWasteVariance(start: string, end: string) { return api.get<{ lines: { item_id: string; name: string; theoretical_usage: number | null; actual_usage: number | null; usage_variance: number | null }[] }>(`/inventory/waste/variance?start=${start}&end=${end}`) }
