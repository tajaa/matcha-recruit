import { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost } from '../types';
import { ArrowLeft, Calendar, User, Share2 } from 'lucide-react';

export function PublicBlogDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [post, setPost] = useState<BlogPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (slug) {
      loadPost(slug);
    }
  }, [slug]);

  const loadPost = async (slug: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await blogs.get(slug);
      setPost(data);
      
      // Update document title
      document.title = `${data.meta_title || data.title} | Matcha Blog`;
    } catch (err) {
      console.error(err);
      setError('Post not found');
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

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: post?.title,
        text: post?.excerpt || post?.title,
        url: window.location.href,
      }).catch(console.error);
    } else {
      navigator.clipboard.writeText(window.location.href);
      alert('Link copied to clipboard');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="min-h-screen bg-stone-50 flex flex-col items-center justify-center text-zinc-900 space-y-4">
        <p className="text-zinc-600">{error || 'Post not found'}</p>
        <Link 
          to="/blog"
          className="text-sm text-emerald-600 hover:text-emerald-700 underline underline-offset-4"
        >
          Back to Blog
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#fdfbf7] via-[#f7f7f5] to-[#f4f4f5] text-zinc-900 overflow-hidden relative font-sans selection:bg-emerald-200 selection:text-emerald-900">
      
      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6 max-w-5xl mx-auto w-full">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-emerald-600 group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-900 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/blog"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-zinc-900 transition-colors"
          >
            Blog
          </Link>
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-zinc-900 transition-colors"
          >
            Login
          </Link>
        </nav>
      </header>

      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-12 max-w-3xl">
        <article className="space-y-12 animate-in fade-in duration-700">
          {/* Article Header */}
          <div className="space-y-6 text-center">
            <div className="flex items-center justify-center gap-3 text-xs text-emerald-600 font-mono uppercase tracking-wider">
              {post.tags && post.tags.map(tag => (
                <span key={tag} className="px-2 py-1 rounded bg-emerald-50 border border-emerald-100">
                  {tag}
                </span>
              ))}
            </div>
            
            <h1 className="text-3xl sm:text-5xl font-light tracking-tight text-zinc-900 leading-tight">
              {post.title}
            </h1>

            <div className="flex items-center justify-center gap-6 text-sm text-zinc-500 font-mono">
              <span className="flex items-center gap-2">
                <User className="w-4 h-4" />
                {post.author_name || 'Matcha Team'}
              </span>
              <span className="flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                {formatDate(post.published_at || post.created_at)}
              </span>
            </div>
          </div>

          {/* Cover Image */}
          {post.cover_image && (
            <div className="aspect-video w-full rounded-lg overflow-hidden shadow-sm bg-stone-100">
              <img
                src={post.cover_image}
                alt={post.title}
                className="w-full h-full object-cover"
              />
            </div>
          )}

          {/* Content */}
          <div className="prose prose-stone prose-lg max-w-none">
            <div className="whitespace-pre-wrap font-serif text-zinc-800 leading-relaxed text-lg">
              {post.content}
            </div>
          </div>

          {/* Footer / Share */}
          <div className="pt-12 border-t border-zinc-200 flex items-center justify-between">
            <Link 
              to="/blog"
              className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-emerald-700 transition-colors group"
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
              Back to Blog
            </Link>
            
            <button
              onClick={handleShare}
              className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-emerald-700 transition-colors"
            >
              <Share2 className="w-4 h-4" />
              Share Post
            </button>
          </div>
        </article>
      </main>

       {/* Footer */}
       <footer className="relative z-10 border-t border-zinc-200 mt-20 bg-white/50">
        <div className="container mx-auto px-4 sm:px-8 py-8 max-w-5xl">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 text-zinc-500 text-xs">
            <span>&copy; {new Date().getFullYear()} Matcha Recruit</span>
            <div className="flex gap-6">
              <Link to="/" className="hover:text-zinc-900 transition-colors">Home</Link>
              <Link to="/blog" className="hover:text-zinc-900 transition-colors">Blog</Link>
              <Link to="/careers" className="hover:text-zinc-900 transition-colors">Careers</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default PublicBlogDetail;