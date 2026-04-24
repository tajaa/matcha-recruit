import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { PricingContactModal } from '../../components/PricingContactModal'
import { api } from '../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type BlogPostFull = {
  id: string
  title: string
  slug: string
  content: string
  excerpt: string | null
  cover_image: string | null
  status: string
  tags: string[]
  meta_title: string | null
  meta_description: string | null
  published_at: string | null
  created_at: string
  updated_at: string
  author_name?: string
}

export default function BlogPostPage() {
  const { slug } = useParams<{ slug: string }>()
  const [post, setPost] = useState<BlogPostFull | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    setError(null)
    api.get<BlogPostFull>(`/blogs/${slug}`)
      .then(setPost)
      .catch(err => setError((err as Error).message))
      .finally(() => setLoading(false))
  }, [slug])

  // Update document title for SEO
  useEffect(() => {
    if (post) {
      document.title = post.meta_title || post.title
    }
    return () => { document.title = 'Matcha' }
  }, [post])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <article className="pt-28 pb-20 max-w-[760px] mx-auto px-6 sm:px-10">
        <Link to="/blog" className="inline-block mb-8 text-sm tracking-wide" style={{ color: MUTED }}>
          ← Back to blog
        </Link>

        {loading ? (
          <div style={{ color: MUTED }}>Loading…</div>
        ) : error ? (
          <div className="border py-16 px-6 text-sm" style={{ borderColor: LINE, color: MUTED }}>
            {error.includes('404') || error.toLowerCase().includes('not found')
              ? 'Post not found.'
              : `Failed to load: ${error}`}
          </div>
        ) : post ? (
          <>
            {post.cover_image && (
              <img
                src={post.cover_image}
                alt={post.title}
                className="w-full max-h-[420px] object-cover rounded mb-10"
              />
            )}

            <header className="mb-10">
              <div className="flex items-center gap-3 text-xs uppercase tracking-widest mb-4" style={{ color: MUTED }}>
                <time>{formatDate(post.published_at ?? post.created_at)}</time>
                {post.tags.length > 0 && (
                  <>
                    <span>•</span>
                    <span>{post.tags.join(' · ')}</span>
                  </>
                )}
              </div>
              <h1
                className="text-4xl sm:text-5xl tracking-tight"
                style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK, lineHeight: 1.1 }}
              >
                {post.title}
              </h1>
              {post.excerpt && (
                <p className="mt-5 text-lg" style={{ color: MUTED }}>
                  {post.excerpt}
                </p>
              )}
            </header>

            <div className="blog-prose">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                // Allow author-pasted <video src=...> tags from Matcha Work
                // exports to render. Other inline HTML stays escaped.
                components={{
                  img: ({ src, alt }) => (
                    <img src={src} alt={alt ?? ''} className="rounded my-6 w-full" />
                  ),
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noreferrer" style={{ color: INK }}>
                      {children}
                    </a>
                  ),
                }}
              >
                {post.content}
              </ReactMarkdown>
            </div>
          </>
        ) : null}
      </article>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />

      <style>{`
        .blog-prose { color: ${INK}; font-size: 17px; line-height: 1.7; }
        .blog-prose h1, .blog-prose h2, .blog-prose h3 {
          font-family: ${DISPLAY}; font-weight: 500; color: ${INK};
          margin: 2em 0 0.5em;
        }
        .blog-prose h2 { font-size: 1.75rem; }
        .blog-prose h3 { font-size: 1.35rem; }
        .blog-prose p { margin: 1em 0; }
        .blog-prose ul, .blog-prose ol { margin: 1em 0; padding-left: 1.5em; }
        .blog-prose li { margin: 0.4em 0; }
        .blog-prose blockquote {
          border-left: 3px solid ${INK};
          padding-left: 1em;
          margin: 1.5em 0;
          color: ${MUTED};
          font-style: italic;
        }
        .blog-prose code {
          background: rgba(0,0,0,0.05);
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 0.9em;
        }
        .blog-prose pre {
          background: rgba(0,0,0,0.05);
          padding: 1em;
          border-radius: 4px;
          overflow-x: auto;
          margin: 1.5em 0;
        }
        .blog-prose video { width: 100%; border-radius: 4px; margin: 1.5em 0; }
      `}</style>
    </div>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch {
    return iso
  }
}
