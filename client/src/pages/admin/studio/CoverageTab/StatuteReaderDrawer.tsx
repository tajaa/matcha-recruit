import type { Dispatch, SetStateAction } from 'react'
import { Loader2 } from 'lucide-react'
import { Drawer } from '../../../../components/ui/Drawer'
import type { ItemBody } from './types'

type ReaderState = { open: boolean; loading: boolean; body: ItemBody | null }

export function StatuteReaderDrawer({
  reader, setReader,
}: {
  reader: ReaderState
  setReader: Dispatch<SetStateAction<ReaderState>>
}) {
  return (
    <Drawer
      open={reader.open}
      onClose={() => setReader({ open: false, loading: false, body: null })}
      width="xl"
      title={reader.body?.citation ?? (reader.loading ? 'Loading…' : 'Statute')}
      subtitle={reader.body ? (
        <span className="flex flex-wrap items-center gap-2">
          {reader.body.heading && <span className="text-zinc-400">{reader.body.heading}</span>}
          {reader.body.index_name && <span>· {reader.body.index_name}</span>}
          {(reader.body.body_source_url || reader.body.source_url) && (
            <a href={reader.body.body_source_url || reader.body.source_url || undefined}
               target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:underline">source ↗</a>
          )}
          {reader.body.body_fetched_at && <span>· fetched {reader.body.body_fetched_at.slice(0, 10)}</span>}
        </span>
      ) : null}
    >
      {reader.loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading the regulation text…
        </div>
      ) : reader.body?.body_text ? (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-zinc-300">
          {reader.body.body_text}
        </pre>
      ) : reader.body ? (
        <div className="text-sm text-zinc-500">
          No stored text for this item yet.{' '}
          {(reader.body.source_url) && (
            <a href={reader.body.source_url} target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:underline">
              Read at the source ↗
            </a>
          )}
        </div>
      ) : (
        <div className="text-sm text-red-400">Failed to load.</div>
      )}
    </Drawer>
  )
}
