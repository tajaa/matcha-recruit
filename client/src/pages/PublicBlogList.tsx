import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost } from '../types';
import { ArrowRight, Calendar } from 'lucide-react';

export function PublicBlogList() {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPosts();
  }, []);

  const loadPosts = async () => {
    try {
      setLoading(true);
      setError(null);
      // For public, we explicitly request published posts, although the API enforces it for non-admins anyway.
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
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#fdfbf7] via-[#f7f7f5] to-[#f4f4f5] text-zinc-900 overflow-hidden relative font-sans selection:bg-emerald-200 selection:text-emerald-900">
      
      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6 max-w-7xl mx-auto w-full">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-emerald-600 group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-900 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/careers"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-zinc-900 transition-colors"
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

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-16 max-w-7xl">
        <div className="space-y-12">
          {/* Hero Section */}
          <div className="space-y-6 text-center max-w-2xl mx-auto">
            <h1 className="text-4xl sm:text-5xl font-light tracking-tight text-zinc-900">
              Latest from the Team
            </h1>
            <p className="text-zinc-500 text-lg leading-relaxed font-serif italic">
              Insights on hiring, culture, and the future of work.
            </p>
          </div>

          {/* Blog Grid */}
          {loading ? (
            <div className="flex justify-center py-20">
              <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-20">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={loadPosts}
                className="text-sm text-zinc-600 hover:text-emerald-700 underline decoration-zinc-300 underline-offset-4"
              >
                Try again
              </button>
            </div>
          ) : posts.length === 0 ? (
            <div className="text-center py-20 border border-zinc-200 bg-white/50 rounded-lg">
              <p className="text-zinc-500">No posts published yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {posts.map((post) => (
                <Link
                  key={post.id}
                  to={`/blog/${post.slug}`}
                  className="group flex flex-col h-full bg-white border border-zinc-200 hover:border-emerald-200 hover:shadow-lg hover:shadow-emerald-900/5 transition-all duration-300 rounded-lg overflow-hidden"
                >
                  {post.cover_image && (
                    <div className="aspect-video w-full overflow-hidden bg-stone-100">
                      <img
                        src={post.cover_image}
                        alt={post.title}
                        className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                      />
                    </div>
                  )}
                  <div className="flex-1 p-6 space-y-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-3 text-xs text-emerald-600 font-mono uppercase tracking-wider">
                        {post.tags && post.tags.length > 0 && (
                          <span>{post.tags[0]}</span>
                        )}
                      </div>
                      <h2 className="text-xl font-medium text-zinc-900 group-hover:text-emerald-700 transition-colors leading-snug">
                        {post.title}
                      </h2>
                      {post.excerpt && (
                        <p className="text-sm text-zinc-500 line-clamp-3 leading-relaxed">
                          {post.excerpt}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="p-6 pt-0 mt-auto flex items-center justify-between text-xs text-zinc-400 border-t border-zinc-100">
                    <div className="flex items-center gap-4 py-4">
                      <span className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        {formatDate(post.published_at || post.created_at)}
                      </span>
                    </div>
                    <span className="group-hover:translate-x-1 transition-transform text-emerald-600">
                      <ArrowRight className="w-4 h-4" />
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-zinc-200 mt-20 bg-white/50">
        <div className="container mx-auto px-4 sm:px-8 py-8 max-w-7xl">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 text-zinc-500 text-xs">
            <span>&copy; {new Date().getFullYear()} Matcha Recruit</span>
            <div className="flex gap-6">
              <Link to="/" className="hover:text-zinc-900 transition-colors">Home</Link>
              <Link to="/careers" className="hover:text-zinc-900 transition-colors">Careers</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default PublicBlogList;