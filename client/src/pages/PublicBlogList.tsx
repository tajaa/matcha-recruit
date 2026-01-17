import { useState, useEffect, lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost } from '../types';
import { ArrowRight, Heart, Calendar } from 'lucide-react';
import { BlogCarousel } from '../components/BlogCarousel';

// Lazy load Three.js component
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
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatTime = (date: Date) => {
    return date.toISOString().slice(11, 19);
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans selection:bg-white selection:text-black">
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-30 mix-blend-overlay" />

      {/* Navigation */}
      <header className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-6 py-6 bg-zinc-950/80 backdrop-blur-xl border-b border-white/10">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 bg-white flex items-center justify-center">
             <div className="w-3 h-3 bg-black group-hover:scale-0 transition-transform duration-500" />
          </div>
          <span className="text-sm font-bold tracking-widest uppercase">Matcha</span>
        </Link>

        <nav className="flex items-center gap-8">
          <Link to="/careers" className="text-xs font-bold tracking-widest uppercase text-zinc-500 hover:text-white transition-colors">
            Careers
          </Link>
          <Link to="/login" className="px-4 py-2 border border-white/20 text-xs font-bold uppercase tracking-widest hover:bg-white hover:text-black transition-colors">
            Login
          </Link>
        </nav>
      </header>

      {/* HERO SECTION */}
      <section className="relative z-10 min-h-[70vh] flex items-center justify-center pt-32 px-6 border-b border-white/10">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center w-full max-w-[1800px] mx-auto">
          {/* Left - Title */}
          <div className="relative z-20">
            <div className="mb-8">
               <span className="inline-block px-3 py-1 bg-white/10 text-white text-[10px] font-bold uppercase tracking-widest mb-4">
                  Matcha Intelligence
               </span>
               <h1 className="text-7xl md:text-9xl font-bold tracking-tighter leading-[0.85] text-white">
                  SIGNAL <br/>
                  <span className="text-zinc-600">NOISE</span>
               </h1>
            </div>
            
            <p className="text-lg text-zinc-400 max-w-xl leading-relaxed font-light mb-12">
               Decoding the patterns of modern recruitment. Insights on AI, culture, and the future of work.
            </p>

            <div className="flex gap-12 text-[10px] uppercase tracking-widest text-zinc-500 font-mono">
               <div className="flex flex-col gap-1">
                  <span>Current Time</span>
                  <span className="text-white">{formatTime(currentTime)}</span>
               </div>
               <div className="flex flex-col gap-1">
                  <span>System Status</span>
                  <span className="text-emerald-500">Operational</span>
               </div>
            </div>
          </div>

          {/* Right - Sphere */}
          <div className="relative h-[500px] w-full flex items-center justify-center">
            <Suspense fallback={<div className="w-full h-full flex items-center justify-center text-zinc-800 uppercase tracking-widest text-xs">Loading Visual...</div>}>
              <ParticleSphere className="w-full h-full scale-125" />
            </Suspense>
          </div>
        </div>
      </section>

      {/* Featured Posts Carousel (if available) */}
      {!loading && posts.length > 0 && (
        <section className="relative z-10 py-24 border-b border-white/10 bg-zinc-900/30">
          <div className="max-w-[1800px] mx-auto px-6">
             <div className="flex items-center gap-4 mb-12">
                <div className="w-2 h-2 bg-white" />
                <span className="text-xs font-bold uppercase tracking-widest">Featured Transmissions</span>
             </div>
             <BlogCarousel posts={posts} limit={5} />
          </div>
        </section>
      )}

      {/* Main Content - Blog Feed */}
      <main className="relative z-10 px-6 py-24 max-w-[1800px] mx-auto">
        <div className="flex items-end justify-between mb-16 border-b border-white/10 pb-8">
           <h2 className="text-4xl font-bold tracking-tighter uppercase">Archive</h2>
           <div className="text-right">
              <div className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-1">Total Entries</div>
              <div className="text-2xl font-light font-mono">{posts.length.toString().padStart(2, '0')}</div>
           </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-4 text-zinc-500">
            <div className="text-xs uppercase tracking-widest animate-pulse"> retrieving data...</div>
          </div>
        ) : error ? (
          <div className="text-center py-24 border border-red-900/30 bg-red-900/10">
            <p className="text-red-500 text-xs font-mono uppercase mb-6">Error: {error}</p>
            <button onClick={loadPosts} className="px-6 py-2 border border-red-500/50 text-red-400 hover:text-white hover:bg-red-500 text-xs uppercase tracking-widest transition-colors">
              Retry Connection
            </button>
          </div>
        ) : posts.length === 0 ? (
          <div className="text-center py-32 border border-dashed border-zinc-800">
            <p className="text-zinc-600 text-xs font-mono uppercase">No entries found in archive</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
            {posts.map((post, index) => (
              <Link
                key={post.id}
                to={`/blog/${post.slug}`}
                className="group relative block bg-zinc-950 hover:bg-zinc-900 transition-colors p-8 h-full flex flex-col justify-between"
              >
                <div>
                   <div className="flex justify-between items-start mb-6">
                      <span className="text-[10px] font-mono text-zinc-600">{(index + 1).toString().padStart(2, '0')}</span>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-500 border border-emerald-900/50 bg-emerald-900/10 px-2 py-1">
                         {post.tags && post.tags.length > 0 ? post.tags[0] : 'General'}
                      </span>
                   </div>
                   
                   <h3 className="text-2xl font-bold uppercase tracking-tight mb-4 group-hover:text-zinc-300 transition-colors">
                      {post.title}
                   </h3>
                   
                   {post.excerpt && (
                      <p className="text-sm text-zinc-500 font-mono leading-relaxed line-clamp-3 mb-8">
                         {post.excerpt}
                      </p>
                   )}
                </div>

                <div className="flex items-center justify-between pt-6 border-t border-white/5">
                   <div className="flex items-center gap-4 text-xs text-zinc-500 font-mono">
                      <span className="flex items-center gap-2">
                         <Calendar size={12} /> {formatDate(post.published_at || post.created_at)}
                      </span>
                      <span className="flex items-center gap-1">
                         <Heart size={12} className={post.liked_by_me ? 'fill-emerald-500 text-emerald-500' : ''} />
                         {post.likes_count}
                      </span>
                   </div>
                   <ArrowRight size={16} className="text-white transform group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>

      <footer className="border-t border-white/10 bg-zinc-950 py-12 px-6">
        <div className="max-w-[1800px] mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
           <div className="text-[10px] uppercase tracking-widest text-zinc-600">
              © {new Date().getFullYear()} Matcha Intelligence
           </div>
           <div className="flex gap-8">
              <Link to="/" className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-colors">System</Link>
              <Link to="/careers" className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-colors">Join Unit</Link>
           </div>
        </div>
      </footer>
    </div>
  );
}

export default PublicBlogList;