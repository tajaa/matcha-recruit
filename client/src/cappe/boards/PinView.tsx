import { memo } from 'react'
import { ExternalLink, FileSpreadsheet, FileText, Globe, Lock } from 'lucide-react'
import { fileUrl, type Pin } from './api'
import { NOTE_BG, sizeLabel } from './look'

const SHEETS = /(excel|spreadsheet|csv)/

/** What a pin shows, by kind. Its frame (position, turn, handles) is the
 *  board's; this is only the content, filling the frame. */
function PinView({ pin, editing, onNoteDone }: {
  pin: Pin
  editing?: boolean
  onNoteDone?: (text: string) => void
}) {
  if (pin.kind === 'note') {
    return (
      <div className={`flex h-full w-full flex-col rounded-sm p-3 shadow-lg ${NOTE_BG[pin.color ?? 'yellow']}`}>
        {editing ? (
          <textarea
            autoFocus
            defaultValue={pin.note ?? ''}
            aria-label="Note"
            maxLength={2000}
            onPointerDown={(e) => e.stopPropagation()}
            onBlur={(e) => onNoteDone?.(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape' || (e.key === 'Enter' && (e.metaKey || e.ctrlKey))) e.currentTarget.blur()
            }}
            className="h-full w-full resize-none bg-transparent text-sm leading-snug outline-none placeholder:text-zinc-500"
            placeholder="Write a note"
          />
        ) : (
          <p className="h-full overflow-hidden whitespace-pre-wrap break-words text-sm leading-snug">{pin.note}</p>
        )}
      </div>
    )
  }
  if (pin.kind === 'image') {
    return (
      <div className="relative h-full w-full overflow-hidden rounded-sm bg-zinc-800 shadow-lg">
        {pin.src && <img src={fileUrl(pin.src) ?? undefined} alt={pin.alt || pin.filename || ''} draggable={false}
          className="h-full w-full object-cover" />}
        {!pin.in_library && (
          <span title="Reference only: kept private until you add it to the library"
            className="absolute left-1.5 top-1.5 rounded bg-zinc-950/70 p-1 text-zinc-300">
            <Lock className="h-3 w-3" aria-hidden /><span className="sr-only">Private reference</span>
          </span>
        )}
        {pin.note && <p className="absolute inset-x-0 bottom-0 truncate bg-zinc-950/70 px-2 py-1 text-xs text-zinc-100">{pin.note}</p>}
      </div>
    )
  }
  if (pin.kind === 'link') {
    return (
      <div className="flex h-full w-full flex-col overflow-hidden rounded-md border border-zinc-700 bg-zinc-900 shadow-lg">
        {pin.src && <img src={fileUrl(pin.src) ?? undefined} alt="" draggable={false} className="min-h-0 flex-1 object-cover" />}
        <div className="shrink-0 space-y-0.5 p-2.5">
          <p className="flex items-center gap-1 truncate text-[11px] text-zinc-400"><Globe className="h-3 w-3 shrink-0" aria-hidden />{pin.site_name}</p>
          <p className="line-clamp-2 text-sm font-medium text-zinc-100">{pin.title || pin.url}</p>
          {!pin.src && pin.description && <p className="line-clamp-2 text-xs text-zinc-400">{pin.description}</p>}
        </div>
      </div>
    )
  }
  const Icon = SHEETS.test(pin.mime ?? '') ? FileSpreadsheet : FileText
  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-md border border-zinc-700 bg-zinc-900 shadow-lg">
      {pin.src
        ? <img src={fileUrl(pin.src) ?? undefined} alt="" draggable={false} className="min-h-0 flex-1 bg-white object-cover object-top" />
        : <div className="flex min-h-0 flex-1 items-center justify-center text-zinc-500"><Icon className="h-8 w-8" aria-hidden /></div>}
      <div className="flex shrink-0 items-center gap-1.5 p-2.5">
        <Icon className="h-4 w-4 shrink-0 text-zinc-400" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-100">{pin.title || pin.filename}</p>
          <p className="text-[11px] text-zinc-500">{sizeLabel(pin.size_bytes)}</p>
        </div>
        <ExternalLink className="ml-auto h-3.5 w-3.5 shrink-0 text-zinc-500" aria-hidden />
      </div>
    </div>
  )
}

export default memo(PinView)
