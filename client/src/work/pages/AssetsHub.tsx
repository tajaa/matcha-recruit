import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Archive, ArrowUpRight, Loader2, Search } from 'lucide-react'
import { useToast } from '../../components/ui'
import { formatDateTimePacific } from '../../utils/dateFormat'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { listCompanyHuumeAssets } from '../api/matchaWork/huume'
import type { HuumeAsset } from '../types'
import { recordIcon } from '../components/panels/HuumePanel/RecordViewer'
import OfferLetterViewer from '../components/panels/HuumePanel/OfferLetterViewer'
import RecordViewer from '../components/panels/HuumePanel/RecordViewer'

const ASSET_TYPE_LABEL: Record<string, string> = {
  offer_letter: 'Offer letter',
  discipline_record: 'Discipline record',
  ir_incident: 'Incident report',
  er_case: 'ER case',
  training_requirement: 'Training assignment',
  pto_request: 'PTO decision',
  inventory_movement: 'Stock movement',
  inventory_receipt: 'Receipt',
  inventory_order: 'Inventory order',
  inventory_item: 'Inventory item',
  schedule_proposal: 'Schedule change',
}

// recordIcon covers the show_record vocabulary (incident/er_case/employee/
// credential/discipline/ems_event/inventory_item) — close enough a mapping
// for most asset_types that no second icon table is worth maintaining.
const ICON_TYPE: Record<string, string> = {
  offer_letter: 'employee',
  discipline_record: 'discipline',
  ir_incident: 'incident',
  er_case: 'er_case',
  inventory_movement: 'inventory_item',
  inventory_receipt: 'inventory_item',
  inventory_order: 'inventory_item',
  inventory_item: 'inventory_item',
}

// Which asset_types have a real viewer vs. just a detail card. Kept
// explicit (not "everything not offer_letter goes to RecordViewer") because
// several types (inventory_movement/_receipt/_order, training_requirement,
// pto_request, schedule_proposal) point at rows record_view.py has no
// builder for — better to say so than 404 a viewer at them.
const RECORD_VIEWER_TYPE: Record<string, string> = {
  ir_incident: 'incident',
  discipline_record: 'discipline',
  er_case: 'er_case',
  inventory_item: 'inventory_item',
}

function AssetDetail({ asset, base }: { asset: HuumeAsset; base: string }) {
  const originLink = asset.thread_id ? (
    <a
      href={`${base}/${asset.thread_id}`}
      className="inline-flex items-center gap-1 text-xs font-medium text-w-accent hover:underline"
    >
      Open originating chat <ArrowUpRight size={11} />
    </a>
  ) : null

  const recordType = RECORD_VIEWER_TYPE[asset.asset_type]

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-w-line px-4 py-2.5">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-w-text">{asset.label}</p>
          <p className="truncate text-[11px] text-w-faint">
            {asset.thread_id
              ? <>Generated from chat <span className="text-w-dim">{asset.thread_title}</span> on {formatDateTimePacific(asset.created_at)}</>
              : <>Generated on {formatDateTimePacific(asset.created_at)}</>}
          </p>
        </div>
        {originLink}
      </div>
      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
        {asset.asset_type === 'offer_letter' ? (
          <OfferLetterViewer offerId={asset.ref_id} />
        ) : recordType ? (
          <RecordViewer recordType={recordType} recordId={asset.ref_id} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
            <Archive size={22} className="text-w-faint" />
            <p className="text-sm text-w-dim">
              {ASSET_TYPE_LABEL[asset.asset_type] ?? asset.asset_type.replace(/_/g, ' ')}
              {asset.status ? ` — ${asset.status}` : ''}
            </p>
            <p className="text-xs text-w-faint">
              No standalone viewer for this type yet — open the originating chat to see it in context.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

/** Company-wide feed of everything Huume has created — offer letters,
 * discipline records, incidents, schedule changes, inventory rows, and
 * anything else registered via services/huume/assets.py — so an admin
 * doesn't have to remember which chat something was generated in.
 * Master/detail: the list stays on the left, the selected asset opens
 * inline on the right via the same viewers the thread panel uses
 * (OfferLetterViewer / RecordViewer) — no re-derivation of chat context. */
export default function AssetsHub() {
  const navigate = useNavigate()
  const { assetId } = useParams<{ assetId: string }>()
  const base = useWorkBase()
  const { toast } = useToast()
  const [assets, setAssets] = useState<HuumeAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const load = useCallback((query?: string) => {
    setLoading(true)
    listCompanyHuumeAssets({ query: query || undefined })
      .then((res) => setAssets(res.assets))
      .catch(() => toast('Failed to load assets', 'error'))
      .finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const t = setTimeout(() => load(search), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const types = Array.from(new Set(assets.map((a) => a.asset_type)))
  const visible = typeFilter === 'all' ? assets : assets.filter((a) => a.asset_type === typeFilter)
  const selected = assetId ? assets.find((a) => a.asset_id === assetId) ?? null : null

  return (
    <div className="h-[calc(100vh-64px)] flex bg-w-bg text-w-text">
      <div className={`flex flex-col min-h-0 border-r border-w-line ${selected ? 'hidden md:flex md:w-[340px] md:shrink-0' : 'flex-1'}`}>
        <div className="flex items-center gap-2 border-b border-w-line px-4 py-3">
          <Archive size={16} className="text-w-dim shrink-0" />
          <h1 className="text-sm font-medium shrink-0">Assets</h1>
        </div>
        <div className="flex items-center gap-2 border-b border-w-line px-3 py-2">
          <div className="relative flex-1">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-w-faint" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search assets..."
              className="w-full rounded-md border border-w-line bg-w-surface2 pl-7 pr-2.5 py-1.5 text-xs text-w-text placeholder:text-w-faint focus:outline-none focus:ring-1 focus:ring-w-accent"
            />
          </div>
          {types.length > 1 && (
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-md border border-w-line bg-w-surface2 px-2 py-1.5 text-xs text-w-text focus:outline-none"
            >
              <option value="all">All types</option>
              {types.map((t) => (
                <option key={t} value={t}>{ASSET_TYPE_LABEL[t] ?? t.replace(/_/g, ' ')}</option>
              ))}
            </select>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex flex-1 items-center justify-center py-16">
              <Loader2 size={20} className="animate-spin text-w-dim" />
            </div>
          ) : visible.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-center px-4">
              <Archive size={24} className="text-w-faint" />
              <p className="text-sm text-w-dim">
                {assets.length === 0
                  ? 'Nothing yet — offer letters, incidents, discipline records, and other things Huume creates will show up here.'
                  : 'No assets match that filter.'}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-w-line">
              {visible.map((a) => (
                <li key={a.asset_id}>
                  <button
                    type="button"
                    onClick={() => navigate(`${base}/assets/${a.asset_id}`)}
                    className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${
                      a.asset_id === assetId ? 'bg-w-surface2' : 'hover:bg-w-surface2/60'
                    }`}
                  >
                    <div className="mt-0.5 text-w-dim shrink-0">
                      {recordIcon(ICON_TYPE[a.asset_type] ?? a.asset_type, 15)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-w-text truncate">{a.label}</span>
                        {a.status && <span className="shrink-0 text-[11px] text-w-dim">{a.status}</span>}
                      </div>
                      <p className="mt-0.5 text-[11px] text-w-faint truncate">
                        {ASSET_TYPE_LABEL[a.asset_type] ?? a.asset_type.replace(/_/g, ' ')} · {formatDateTimePacific(a.created_at)}
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {selected ? (
        <AssetDetail asset={selected} base={base} />
      ) : (
        assetId ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 size={20} className="animate-spin text-w-dim" />
          </div>
        ) : (
          <div className="hidden md:flex flex-1 items-center justify-center px-4 text-center">
            <p className="text-sm text-w-faint">Select an asset to open it.</p>
          </div>
        )
      )}
    </div>
  )
}
