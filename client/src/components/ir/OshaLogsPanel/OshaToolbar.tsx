import { Download, Loader2, FileSpreadsheet, FileText, Send } from 'lucide-react'
import type { BusinessLocation } from '../../../types/compliance'
import { Button } from '../../ui'

interface OshaToolbarProps {
  locations: BusinessLocation[]
  locationId: string
  setLocationId: (id: string) => void
  year: number
  setYear: (year: number) => void
  years: number[]
  itaBusy: boolean
  onExport300Csv: () => void
  onExport300aCsv: () => void
  onExport300aPdf: () => void
  onExportIta: () => void
  onSubmitIta: () => void
}

export function OshaToolbar({
  locations,
  locationId,
  setLocationId,
  year,
  setYear,
  years,
  itaBusy,
  onExport300Csv,
  onExport300aCsv,
  onExport300aPdf,
  onExportIta,
  onSubmitIta,
}: OshaToolbarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <FileSpreadsheet size={16} className="text-zinc-500" />
        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          OSHA 300/300A Logs
        </span>
        <select
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
          className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-200 text-xs px-2.5 py-1 max-w-[200px]"
        >
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name || `${l.city}, ${l.state}`}
            </option>
          ))}
        </select>
        <select
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-200 text-xs px-2.5 py-1 font-mono"
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="ghost" onClick={onExport300Csv}>
          <Download size={12} className="mr-1.5" />
          300 CSV
        </Button>
        <Button size="sm" variant="ghost" onClick={onExport300aCsv}>
          <Download size={12} className="mr-1.5" />
          300A CSV
        </Button>
        <Button size="sm" variant="ghost" onClick={onExport300aPdf}>
          <FileText size={12} className="mr-1.5" />
          300A PDF
        </Button>
        <Button size="sm" variant="ghost" onClick={onExportIta} disabled={itaBusy}>
          {itaBusy ? (
            <Loader2 size={12} className="mr-1.5 animate-spin" />
          ) : (
            <Download size={12} className="mr-1.5" />
          )}
          ITA Export
        </Button>
        <Button size="sm" onClick={onSubmitIta} disabled={itaBusy}>
          {itaBusy ? (
            <Loader2 size={12} className="mr-1.5 animate-spin" />
          ) : (
            <Send size={12} className="mr-1.5" />
          )}
          Submit to ITA
        </Button>
      </div>
    </div>
  )
}
