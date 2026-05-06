import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ExternalLink } from 'lucide-react'

import { api } from '../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type NewsItem = {
  id: string
  title: string
  description: string | null
  link: string
  pub_date: string | null
  source_name: string | null
  source_feed_url: string | null
  image_url: string | null
}

type NewsResponse = { items: NewsItem[] }

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function HRNewsSection() {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    api.get<NewsResponse>('/news?limit=9')
      .then((d) => { if (alive) setItems(d.items ?? []) })
      .catch(() => { if (alive) setItems([]) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  if (loading) return null
  if (items.length === 0) return null

  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div
            className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4"
            style={{ color: MUTED }}
          >
            Latest in HR
          </div>
          <h2
            className="tracking-tight"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(1.875rem, 5vw, 3.25rem)',
              lineHeight: 1.05,
            }}
          >
            What's moving the industry.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Headlines from across HR — pulled from leading industry publications,
            updated throughout the day.
          </p>
        </div>

        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-xl overflow-hidden"
          style={{ backgroundColor: LINE }}
        >
          {items.map((item, i) => (
            <motion.a
              key={item.id}
              href={item.link}
              target="_blank"
              rel="noopener noreferrer"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: i * 0.06, ease: 'easeOut' }}
              className="p-6 sm:p-8 flex flex-col group transition-colors"
              style={{ backgroundColor: BG }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(31,29,26,0.02)')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = BG)}
            >
              {item.image_url && (
                <div
                  className="w-full aspect-[16/9] mb-5 overflow-hidden rounded"
                  style={{ backgroundColor: 'rgba(31,29,26,0.04)' }}
                >
                  <img
                    src={item.image_url}
                    alt=""
                    loading="lazy"
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.currentTarget.parentElement as HTMLDivElement).style.display = 'none' }}
                  />
                </div>
              )}

              <div className="flex items-center gap-2 mb-3 text-[11px] uppercase tracking-wider" style={{ color: MUTED }}>
                {item.source_name && <span>{item.source_name}</span>}
                {item.source_name && item.pub_date && <span>·</span>}
                {item.pub_date && <time>{formatDate(item.pub_date)}</time>}
              </div>

              <h3
                className="text-lg sm:text-xl mb-2 line-clamp-3"
                style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500, lineHeight: 1.25 }}
              >
                {item.title}
              </h3>

              {item.description && (
                <p
                  className="text-sm line-clamp-3 flex-1"
                  style={{ color: MUTED, lineHeight: 1.6 }}
                >
                  {item.description}
                </p>
              )}

              <span
                className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium"
                style={{ color: INK }}
              >
                Read on {item.source_name || 'source'}
                <ExternalLink className="w-3 h-3 opacity-60 group-hover:opacity-100 transition-opacity" />
              </span>
            </motion.a>
          ))}
        </div>
      </div>
    </section>
  )
}
