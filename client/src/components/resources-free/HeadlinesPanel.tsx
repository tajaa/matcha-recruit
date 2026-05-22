import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Loader2 } from 'lucide-react'

import { api } from '../../api/client'
import type { NewsItem, NewsResponse } from '../../types/news'

type Props = { compact?: boolean }

function decodeEntities(str: string): string {
  const txt = document.createElement('textarea')
  txt.innerHTML = str
  return txt.value
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function NewsCard({ item }: { item: NewsItem }) {
  const [imgOk, setImgOk] = useState(!!item.image_url)
  return (
    <a
      href={item.link}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden hover:border-white/20 hover:bg-zinc-800/50 transition-colors"
    >
      <div className="relative w-full h-36 overflow-hidden">
        {imgOk && item.image_url ? (
          <img
            src={item.image_url}
            alt=""
            onError={() => setImgOk(false)}
            className="w-full h-full object-cover brightness-75 saturate-[0.7]"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-zinc-800 to-zinc-900 flex items-center justify-center">
            <span className="text-[10px] font-mono text-zinc-700 uppercase tracking-widest">
              {item.source_name ?? 'HR News'}
            </span>
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
      </div>
      <div className="flex flex-col gap-2 p-4">
      <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
        {item.source_name && <span>{item.source_name}</span>}
        {item.source_name && item.pub_date && <span>·</span>}
        {item.pub_date && <span>{formatDate(item.pub_date)}</span>}
      </div>
      <p className="text-sm font-medium text-zinc-100 line-clamp-2 group-hover:text-white transition-colors">
        {decodeEntities(item.title)}
      </p>
      {item.description && (
        <p className="text-[12px] text-zinc-500 leading-relaxed line-clamp-2">{decodeEntities(item.description)}</p>
      )}
        <div className="mt-auto pt-1 flex items-center gap-1 text-[10px] text-emerald-500/70 group-hover:text-emerald-400 transition-colors">
          <ExternalLink className="w-3 h-3" />
          <span>Read article</span>
        </div>
      </div>
    </a>
  )
}

export default function HeadlinesPanel({ compact = false }: Props) {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const limit = compact ? 4 : 12
    api.get<NewsResponse>(`/news?limit=${limit}`)
      .then(r => setItems(r.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [compact])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 text-zinc-600 animate-spin" />
      </div>
    )
  }

  if (items.length === 0) {
    if (compact) return null
    return (
      <p className="text-sm text-zinc-600">No headlines available right now — check back soon.</p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">This week in HR</h2>
          <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mt-0.5">
            Latest industry headlines
          </p>
        </div>
        {compact && (
          <Link
            to="/app/resources/headlines"
            className="text-[11px] text-emerald-500 hover:text-emerald-400 transition-colors"
          >
            See all →
          </Link>
        )}
      </div>
      <div className={`grid gap-4 ${compact ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'}`}>
        {items.map(item => (
          <NewsCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  )
}
