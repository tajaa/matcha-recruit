import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { PricingContactModal } from '../../components/PricingContactModal'
import { api } from '../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type BlogPost = {
  id: string
  title: string
  slug: string
  excerpt: string | null
  cover_image: string | null
  status: string
  tags: string[]
  published_at: string | null
  created_at: string
  updated_at: string
  author_name?: string
}

type BlogList = { items: BlogPost[]; total: number }

export default function BlogIndex() {
  const [posts, setPosts] = useState<BlogPost[]>([])
  const [loading, setLoading] = useState(true)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    api.get<BlogList>('/blogs?status=published&limit=50')
      .then(d => setPosts(d.items))
      .catch(() => setPosts([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10">
        <header className="mb-14">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Blog
          </h1>
          <p className="mt-4 text-base max-w-xl" style={{ color: MUTED }}>
            Field notes from the practice — HR, compliance, GRC, and the
            people-operations work that doesn't fit into a tweet.
          </p>
        </header>

        {loading ? (
          <div style={{ color: MUTED }} className="text-sm">Loading…</div>
        ) : posts.length === 0 ? (
          <div className="border border-dashed py-16 text-center text-sm" style={{ borderColor: LINE, color: MUTED }}>
            No posts yet.
          </div>
        ) : (
          <div className="grid gap-10">
            {posts.map(p => (
              <article key={p.id} className="border-b pb-10 last:border-b-0" style={{ borderColor: LINE }}>
                <Link to={`/blog/${p.slug}`} className="group block">
                  {p.cover_image && (
                    <img
                      src={p.cover_image}
                      alt={p.title}
                      className="w-full h-72 object-cover rounded mb-6"
                    />
                  )}
                  <div className="flex items-center gap-3 text-xs uppercase tracking-widest mb-3" style={{ color: MUTED }}>
                    <time>{formatDate(p.published_at ?? p.created_at)}</time>
                    {p.tags.length > 0 && (
                      <>
                        <span>•</span>
                        <span>{p.tags.slice(0, 3).join(' · ')}</span>
                      </>
                    )}
                  </div>
                  <h2
                    className="text-3xl tracking-tight transition-opacity group-hover:opacity-70"
                    style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
                  >
                    {p.title}
                  </h2>
                  {p.excerpt && (
                    <p className="mt-3 text-base max-w-2xl" style={{ color: MUTED }}>
                      {p.excerpt}
                    </p>
                  )}
                  <span className="inline-block mt-4 text-sm tracking-wide" style={{ color: INK }}>
                    Read →
                  </span>
                </Link>
              </article>
            ))}
          </div>
        )}
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return iso
  }
}
