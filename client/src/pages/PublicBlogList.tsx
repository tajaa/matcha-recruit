import { useState, useEffect, lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost } from '../types';
import { ArrowRight, Heart } from 'lucide-react';
import { BlogCarousel } from '../components/BlogCarousel';

// Lazy load Three.js component if we want to use it here too, 
// but let's keep it simple for now or use a lighter version.
const ParticleSphere = lazy(() => import('../components/ParticleSphere'));

export function PublicBlogList() {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    loadPosts();
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const loadPosts = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await blogs.list({ status: 'published', limit: 50 });
      setPosts(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load blog posts');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '';
    return new Date(dateString).toISOString().slice(0, 10);
  };

  const formatTime = (date: Date) => {
    return date.toISOString().slice(11, 19);
  };

  return (
    <div className="min-h-screen bg-[#fcfcfc] text-zinc-900 font-mono selection:bg-emerald-100 selection:text-emerald-900">
      {/* Fixed Background Elements */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #000 1px, transparent 1px),
              linear-gradient(to bottom, #000 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#fcfcfc_80%)]" />
      </div>

      {/* Navigation */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 sm:px-8 py-6 bg-white/80 backdrop-blur-md border-b border-zinc-200">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.4)]" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-900 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/careers"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-emerald-600 transition-colors"
          >
            Careers
          </Link>
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-zinc-900 transition-colors"
          >
            Login
          </Link>
        </nav>
      </header>

      {/* HERO SECTION */}
      <section className="relative z-10 min-h-[60vh] flex items-center justify-center pt-32 px-4 sm:px-8 border-b border-zinc-200">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_minmax(300px,400px)_1fr] gap-8 items-center w-full max-w-7xl">
          {/* Left - Title */}
          <div className="flex flex-col justify-center lg:text-left text-center">
            <div className="space-y-4">
              <h1 className="text-4xl sm:text-6xl lg:text-7xl font-bold tracking-[-0.02em] text-zinc-900">
                BLOG
              </h1>
              <p className="text-xs tracking-[0.3em] uppercase text-emerald-600 font-medium">
                Insights & Signals
              </p>
            </div>

            <div className="mt-12 space-y-3 hidden lg:block">
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-400 font-medium">
                <span className="w-2 h-px bg-zinc-200" />
                <span>RECRUITING ARCHITECTURE</span>
              </div>
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-400 font-medium">
                <span className="w-2 h-px bg-zinc-200" />
                <span>AI INTERVIEW LOGIC</span>
              </div>
              <div className="flex items-center gap-3 text-[10px] tracking-widest text-zinc-400 font-medium">
                <span className="w-2 h-px bg-zinc-200" />
                <span>CULTURAL FREQUENCIES</span>
              </div>
            </div>
          </div>

          {/* Center - Sphere (Subtle Light Mode) */}
          <div className="relative flex items-center justify-center py-12 lg:py-0">
            <Suspense fallback={<div className="w-full h-[300px] bg-transparent" />}>
              {/* ParticleSphere might need props for light mode if it's hardcoded for dark */}
              <ParticleSphere className="w-full h-[300px] lg:h-[400px] opacity-40 grayscale" />
            </Suspense>
          </div>

          {/* Right - Timestamp */}
          <div className="flex flex-col items-end justify-center hidden lg:flex">
            <div className="text-right space-y-6">
              <div>
                <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-1">
                  UTC TIME
                </div>
                <div className="text-2xl tracking-wider text-zinc-600 tabular-nums">
                  {formatTime(currentTime)}
                </div>
              </div>

              <div>
                <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-1">
                  SYSTEM STATUS
                </div>
                <div className="flex items-center justify-end gap-2">
                  <span className="text-xs tracking-widest text-emerald-600">
                    LIVE
                  </span>
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Featured Posts Carousel */}
      {!loading && posts.length > 0 && (
        <section className="relative z-10 px-4 sm:px-8 py-16 max-w-7xl mx-auto border-b border-zinc-200">
          <div className="mb-8">
            <div className="flex items-center gap-4">
              <div className="w-1 h-8 bg-emerald-500" />
              <div>
                <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-400 block">
                  Featured
                </span>
                <span className="text-[10px] tracking-[0.2em] uppercase text-zinc-600">
                  Latest Posts
                </span>
              </div>
            </div>
          </div>
          <BlogCarousel posts={posts} limit={8} />
        </section>
      )}

      {/* Main Content - Blog Feed */}
      <main className="relative z-10 px-4 sm:px-8 py-16 max-w-7xl mx-auto">
        {/* Section Header */}
        <div className="flex items-center justify-between mb-12 pb-6 border-b border-zinc-200">
          <div className="flex items-center gap-4">
            <div className="w-1 h-8 bg-emerald-500" />
            <div>
              <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-400 block">Archive</span>
              <span className="text-[10px] tracking-[0.2em] uppercase text-zinc-600">{posts.length} Entries</span>
            </div>
          </div>
          <div className="text-[9px] tracking-[0.2em] uppercase text-zinc-400">
            Latest First
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="relative w-12 h-12">
              <div className="absolute inset-0 border border-zinc-200 animate-ping" />
              <div className="absolute inset-2 border border-emerald-500/50" />
              <div className="absolute inset-4 bg-emerald-500/20" />
            </div>
            <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-400">Fetching_Data</span>
          </div>
        ) : error ? (
          <div className="text-center py-24 border border-red-200 bg-red-50/50">
            <div className="w-8 h-8 mx-auto mb-4 border border-red-300 flex items-center justify-center">
              <span className="text-red-500 text-xs">!</span>
            </div>
            <p className="text-red-600 text-[10px] tracking-[0.3em] uppercase mb-6">{error}</p>
            <button
              onClick={loadPosts}
              className="text-[10px] tracking-[0.2em] uppercase border border-red-300 px-6 py-2.5 hover:bg-red-100 transition-colors text-red-600"
            >
              Retry
            </button>
          </div>
        ) : posts.length === 0 ? (
          <div className="text-center py-32 border border-dashed border-zinc-300">
            <div className="w-12 h-12 mx-auto mb-4 border border-zinc-200 flex items-center justify-center">
              <span className="text-zinc-300 text-lg">∅</span>
            </div>
            <p className="text-zinc-400 text-[10px] tracking-[0.3em] uppercase">No Entries Found</p>
          </div>
        ) : (
          <div className="space-y-0">
            {posts.map((post, index) => (
              <Link
                key={post.id}
                to={`/blog/${post.slug}`}
                className="group relative block border-b border-zinc-200 hover:bg-zinc-50/80 transition-all duration-200"
              >
                <div className="py-8 sm:py-10">
                  {/* Post number */}
                  <div className="absolute left-0 top-8 sm:top-10 text-[9px] tracking-wider text-zinc-300 font-medium">
                    {(index + 1).toString().padStart(2, '0')}
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-[1fr_200px] gap-6 pl-8 sm:pl-12">
                    <div className="space-y-4">
                      {/* Meta row */}
                      <div className="flex items-center gap-4">
                        <span className="text-[9px] tracking-[0.2em] uppercase text-emerald-600 font-medium px-2 py-1 bg-emerald-50 border border-emerald-100">
                          {post.tags && post.tags.length > 0 ? post.tags[0] : 'General'}
                        </span>
                        <span className="text-[9px] tracking-[0.15em] text-zinc-400">
                          {formatDate(post.published_at || post.created_at)}
                        </span>
                      </div>

                      {/* Title */}
                      <h2 className="text-lg sm:text-xl font-semibold text-zinc-900 group-hover:text-emerald-600 transition-colors leading-snug pr-4">
                        {post.title}
                      </h2>

                      {/* Excerpt */}
                      {post.excerpt && (
                        <p className="text-sm text-zinc-500 leading-relaxed line-clamp-2 max-w-2xl">
                          {post.excerpt}
                        </p>
                      )}
                    </div>

                    {/* Right side - stats & arrow */}
                    <div className="flex lg:flex-col items-center lg:items-end justify-between lg:justify-center gap-4 pl-8 sm:pl-12 lg:pl-0">
                      <div className="flex items-center gap-4 text-[9px] tracking-wider text-zinc-400">
                        <span className="flex items-center gap-1.5">
                          <Heart className={`w-3.5 h-3.5 ${post.liked_by_me ? 'fill-emerald-500 text-emerald-500' : ''}`} />
                          <span className="tabular-nums">{post.likes_count}</span>
                        </span>
                      </div>
                      <div className="w-8 h-8 border border-zinc-200 group-hover:border-emerald-500 group-hover:bg-emerald-50 flex items-center justify-center transition-all">
                        <ArrowRight className="w-3.5 h-3.5 text-zinc-400 group-hover:text-emerald-600 group-hover:translate-x-0.5 transition-all" />
                      </div>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>

      {/* FOOTER STATS */}
      <section className="relative z-10 border-t border-zinc-200 bg-zinc-100/50">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-zinc-200">
            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Entries
              </span>
              <span className="text-2xl sm:text-3xl font-light text-zinc-900 tabular-nums">
                {posts.length.toString().padStart(2, '0')}
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Last Update
              </span>
              <span className="text-sm sm:text-base font-light text-zinc-900 tabular-nums">
                {posts.length > 0 ? formatDate(posts[0].published_at || posts[0].created_at) : '—'}
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Categories
              </span>
              <span className="text-2xl sm:text-3xl font-light text-zinc-900 tabular-nums">
                {new Set(posts.flatMap(p => p.tags || [])).size.toString().padStart(2, '0')}
              </span>
            </div>

            <div className="p-6 sm:p-8">
              <span className="text-[9px] tracking-[0.2em] text-zinc-400 uppercase block mb-2">
                Status
              </span>
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm sm:text-base font-light text-emerald-600 uppercase tracking-wider">
                  Live
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <footer className="relative z-10 py-6 border-t border-zinc-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-[9px] tracking-[0.3em] text-zinc-400 uppercase">
            © {new Date().getFullYear()} Matcha Recruit
          </span>
          <div className="flex items-center gap-6">
            <Link to="/" className="text-[9px] tracking-[0.2em] text-zinc-400 hover:text-emerald-600 uppercase transition-colors">
              Home
            </Link>
            <Link to="/careers" className="text-[9px] tracking-[0.2em] text-zinc-400 hover:text-emerald-600 uppercase transition-colors">
              Careers
            </Link>
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes loading-bar {
          0% { transform: translateY(100%); }
          100% { transform: translateY(-100%); }
        }
      `}</style>
    </div>
  );
}

export default PublicBlogList;
