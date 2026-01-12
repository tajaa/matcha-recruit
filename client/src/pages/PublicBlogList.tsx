import { useState, useEffect, lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost } from '../types';
import { ArrowRight, Heart } from 'lucide-react';

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

      {/* Main Content - Blog Feed */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-24 max-w-7xl">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="w-1 h-12 bg-zinc-100 relative overflow-hidden">
              <div className="absolute inset-0 bg-emerald-500 animate-[loading-bar_1.5s_infinite]" />
            </div>
            <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-400">Loading_Entries</span>
          </div>
        ) : error ? (
          <div className="text-center py-24 border border-red-100 bg-red-50/30">
            <p className="text-red-600 text-xs tracking-widest uppercase">{error}</p>
            <button
              onClick={loadPosts}
              className="mt-6 text-[10px] tracking-widest uppercase border border-red-200 px-6 py-2 hover:bg-red-50 transition-colors"
            >
              Retry_Fetch
            </button>
          </div>
        ) : posts.length === 0 ? (
          <div className="text-center py-32 border border-zinc-100 bg-zinc-50/30">
            <p className="text-zinc-400 text-xs tracking-widest uppercase italic">0_Entries_Found</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-zinc-200 border border-zinc-200">
            {posts.map((post) => (
              <Link
                key={post.id}
                to={`/blog/${post.slug}`}
                className="group relative flex flex-col h-full bg-[#fcfcfc] p-8 sm:p-10 hover:bg-white transition-all duration-300"
              >
                <div className="space-y-6 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] tracking-[0.3em] uppercase text-emerald-600 font-bold">
                      {post.tags && post.tags.length > 0 ? post.tags[0] : 'General'}
                    </span>
                    <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-400">
                      {formatDate(post.published_at || post.created_at)}
                    </span>
                  </div>

                  <div className="space-y-3">
                    <h2 className="text-xl font-bold text-zinc-900 group-hover:text-emerald-600 transition-colors leading-tight uppercase">
                      {post.title}
                    </h2>
                    {post.excerpt && (
                      <p className="text-xs text-zinc-500 line-clamp-3 leading-relaxed font-sans">
                        {post.excerpt}
                      </p>
                    )}
                  </div>
                </div>

                <div className="mt-12 pt-6 border-t border-zinc-100 flex items-center justify-between">
                  <div className="flex items-center gap-4 text-[9px] tracking-widest text-zinc-400 uppercase">
                    <span className="flex items-center gap-1.5">
                      <Heart className={`w-3 h-3 ${post.liked_by_me ? 'fill-emerald-500 text-emerald-500' : ''}`} />
                      {post.likes_count}
                    </span>
                  </div>
                  <span className="group-hover:translate-x-1 transition-transform text-zinc-900">
                    <ArrowRight className="w-4 h-4" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>

      {/* FOOTER STATS */}
      <section className="relative z-10 py-12 px-4 sm:px-8 bg-zinc-50 border-t border-zinc-200">
        <div className="flex flex-wrap items-center justify-between max-w-7xl mx-auto gap-8">
          <div className="flex flex-col gap-2">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase">
              Total Feed Volume
            </span>
            <span className="text-2xl tracking-wider text-zinc-900 tabular-nums">
              {posts.length.toString().padStart(2, '0')}
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase">
              Last Pulse
            </span>
            <span className="text-2xl tracking-wider text-zinc-900 tabular-nums">
              {posts.length > 0 ? formatDate(posts[0].published_at || posts[0].created_at) : 'N/A'}
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[10px] tracking-[0.2em] text-zinc-400 uppercase">
              Network Status
            </span>
            <div className="flex items-center gap-2 mt-1">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
              <span className="text-xs tracking-[0.15em] text-emerald-600 uppercase font-medium">
                Active
              </span>
            </div>
          </div>
        </div>
      </section>
      
      <footer className="relative z-10 py-8 text-center text-[9px] tracking-[0.4em] text-zinc-400 uppercase border-t border-zinc-100">
        © {new Date().getFullYear()} Matcha Recruit // Transmission Complete
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
