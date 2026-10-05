import { Loader2, Rocket, Globe } from 'lucide-react'
import type { CappeSite } from '../../types'
import { statusStyle } from './styles'

export function EditorHeader({
  site, publicUrl, publishing, onPublish, blocked = false,
}: {
  site: CappeSite
  publicUrl: string
  publishing: boolean
  onPublish: () => void
  /** The launch checklist still has a required step open. */
  blocked?: boolean
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{site.name}</h1>
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[site.status] || statusStyle.draft}`}>
            {site.status}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-1 break-all text-sm text-zinc-500">
          <Globe className="h-3.5 w-3.5" />
          {site.status === 'published' ? (
            <a href={`https://${publicUrl}`} target="_blank" rel="noreferrer" className="hover:text-emerald-400">
              {publicUrl}
            </a>
          ) : (
            publicUrl
          )}
        </div>
      </div>
      <button
        onClick={onPublish}
        disabled={publishing || blocked}
        title={blocked ? 'Finish the required steps first' : undefined}
        className="flex shrink-0 items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
        {site.status === 'published' ? 'Re-publish' : 'Publish'}
      </button>
    </div>
  )
}
