import { useEffect, useMemo, useState } from 'react'
import { Download, FileSpreadsheet, FileText } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Input, Modal, Select } from '../ui'
import { INCIDENT_TYPE_OPTIONS } from '../../types/ir'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

type Format = 'csv' | 'pdf'

type Props = {
  open: boolean
  onClose: () => void
}

const SEVERITY_OPTIONS = [
  { value: '', label: 'All Severities' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'reported', label: 'Reported' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'action_required', label: 'Action Required' },
  { value: 'closed', label: 'Closed' },
]

function formatLocationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function daysAgoISO(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

export function IRExportModal({ open, onClose }: Props) {
  const [format, setFormat] = useState<Format>('csv')
  const [fromDate, setFromDate] = useState<string>(daysAgoISO(90))
  const [toDate, setToDate] = useState<string>(todayISO())
  const [incidentType, setIncidentType] = useState<string>('')
  const [severity, setSeverity] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [locationId, setLocationId] = useState<string>('')
  const [locations, setLocations] = useState<LocationRow[] | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations(rows || []))
      .catch(() => setLocations([]))
  }, [open])

  const locationOptions = useMemo(() => {
    const active = (locations || []).filter((l) => l.is_active)
    return [
      { value: '', label: 'All Locations' },
      ...active.map((l) => ({ value: l.id, label: formatLocationLabel(l) })),
    ]
  }, [locations])

  const typeOptions = useMemo(
    () => [{ value: '', label: 'All Types' }, ...INCIDENT_TYPE_OPTIONS],
    [],
  )

  async function handleDownload() {
    setError(null)
    setDownloading(true)
    try {
      const params = new URLSearchParams()
      params.set('format', format)
      if (fromDate) params.set('from_date', new Date(fromDate).toISOString())
      if (toDate) {
        const end = new Date(toDate)
        end.setHours(23, 59, 59, 999)
        params.set('to_date', end.toISOString())
      }
      if (incidentType) params.set('incident_type', incidentType)
      if (severity) params.set('severity', severity)
      if (status) params.set('status', status)
      if (locationId) params.set('location_id', locationId)

      const base = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${base}/ir/incidents/export?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `Export failed (${res.status})`)
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const a = document.createElement('a')
      a.href = url
      a.download = `incidents-${stamp}.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Export Incidents" width="md">
      <div className="space-y-5">
        {/* Format */}
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Format</div>
          <div className="grid grid-cols-2 gap-2">
            {([
              { value: 'csv' as const, label: 'CSV', icon: FileSpreadsheet, hint: 'For Excel / Sheets' },
              { value: 'pdf' as const, label: 'PDF', icon: FileText, hint: 'Printable report' },
            ]).map((opt) => {
              const Icon = opt.icon
              const active = format === opt.value
              return (
                <button
                  key={opt.value}
                  onClick={() => setFormat(opt.value)}
                  className={`p-3 rounded-xl border text-left transition-colors ${
                    active
                      ? 'bg-zinc-800 border-zinc-600 text-zinc-100'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4" />
                    <span className="text-sm font-medium">{opt.label}</span>
                  </div>
                  <div className="text-[10px] text-zinc-500 mt-1">{opt.hint}</div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Date range */}
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Date Range</div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label=""
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
            <Input
              label=""
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>
        </div>

        {/* Filters */}
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Type"
            options={typeOptions}
            value={incidentType}
            onChange={(e) => setIncidentType(e.target.value)}
          />
          <Select
            label="Severity"
            options={SEVERITY_OPTIONS}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          />
          <Select
            label="Status"
            options={STATUS_OPTIONS}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          />
          <Select
            label="Location"
            options={locationOptions}
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
          />
        </div>

        {error && (
          <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} disabled={downloading}>
            Cancel
          </Button>
          <Button onClick={handleDownload} disabled={downloading}>
            <Download className={`w-3.5 h-3.5 ${downloading ? 'animate-pulse' : ''}`} />
            <span className="ml-2">{downloading ? 'Generating…' : `Download ${format.toUpperCase()}`}</span>
          </Button>
        </div>
      </div>
    </Modal>
  )
}
