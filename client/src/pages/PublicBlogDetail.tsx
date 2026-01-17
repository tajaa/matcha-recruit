import { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { blogs } from '../api/client';
import type { BlogPost, BlogComment } from '../types';
import { ArrowLeft, Calendar, User, Share2, Heart, MessageSquare, Send } from 'lucide-react';

export function PublicBlogDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [post, setPost] = useState<BlogPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Like state
  const [liked, setLiked] = useState(false);
  const [likesCount, setLikesCount] = useState(0);
  const [liking, setLiking] = useState(false);

  // Comments state
  const [comments, setComments] = useState<BlogComment[]>([]);
  const [commentContent, setCommentContent] = useState('');
  const [authorName, setAuthorName] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [commentSuccess, setCommentSuccess] = useState(false);

  useEffect(() => {
    if (slug) {
      loadPost(slug);
      loadComments(slug);
    }
  }, [slug]);

  const getSessionId = () => {
    let id = localStorage.getItem('matcha_guest_session');
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem('matcha_guest_session', id);
    }
    return id;
  };

  const loadPost = async (slug: string) => {
    try {
      setLoading(true);
      setError(null);
      const sessionId = getSessionId();
      const data = await blogs.get(slug, sessionId);
      setPost(data);
      setLiked(data.liked_by_me);
      setLikesCount(data.likes_count);
      
      document.title = `${data.meta_title || data.title} | Matcha`;
    } catch (err) {
      console.error(err);
      setError('Post not found');
    } finally {
      setLoading(false);
    }
  };

  const loadComments = async (slug: string) => {
    try {
      const data = await blogs.listComments(slug);
      setComments(data);
    } catch (error) {
      console.error('Failed to load comments:', error);
    }
  };

  const handleLike = async () => {
    if (!slug || liking) return;
    
    const prevLiked = liked;
    const prevCount = likesCount;
    
    setLiked(!liked);
    setLikesCount(prevLiked ? prevCount - 1 : prevCount + 1);
    setLiking(true);

    try {
      const sessionId = getSessionId();
      const result = await blogs.toggleLike(slug, sessionId);
      setLiked(result.liked);
      setLikesCount(result.likes_count);
    } catch (error) {
      console.error('Failed to toggle like:', error);
      setLiked(prevLiked);
      setLikesCount(prevCount);
    } finally {
      setLiking(false);
    }
  };

  const handleSubmitComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slug || !commentContent.trim() || submittingComment) return;

    try {
      setSubmittingComment(true);
      const result = await blogs.submitComment(slug, {
        content: commentContent.trim(),
        author_name: authorName.trim() || undefined,
      });

      if (result.status === 'approved') {
        setComments([...comments, result]);
        setCommentContent('');
      } else {
        setCommentSuccess(true);
        setCommentContent('');
        setAuthorName('');
        setTimeout(() => setCommentSuccess(false), 5000);
      }
    } catch (error) {
      console.error('Failed to submit comment:', error);
      alert('Failed to submit comment.');
    } finally {
      setSubmittingComment(false);
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
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-xs font-bold uppercase tracking-widest text-zinc-500 animate-pulse">Loading Transmission...</div>
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center text-white space-y-6">
        <p className="text-zinc-500 font-mono uppercase tracking-wider">{error || 'Data Not Found'}</p>
        <Link 
          to="/blog"
          className="text-xs font-bold uppercase tracking-widest border border-zinc-700 px-6 py-3 hover:bg-white hover:text-black transition-colors"
        >
          Return to Archive
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans selection:bg-white selection:text-black">
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-30 mix-blend-overlay" />

      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-6 py-6 bg-zinc-950/80 backdrop-blur-xl border-b border-white/10">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 bg-white flex items-center justify-center">
             <div className="w-3 h-3 bg-black group-hover:scale-0 transition-transform duration-500" />
          </div>
          <span className="text-sm font-bold tracking-widest uppercase">Matcha</span>
        </Link>

        <nav className="flex items-center gap-8">
          <Link to="/blog" className="text-xs font-bold tracking-widest uppercase text-zinc-500 hover:text-white transition-colors">
            Archive
          </Link>
          <Link to="/login" className="px-4 py-2 border border-white/20 text-xs font-bold uppercase tracking-widest hover:bg-white hover:text-black transition-colors">
            Login
          </Link>
        </nav>
      </header>

      <main className="relative z-10 container mx-auto px-6 py-32 max-w-4xl">
        <article className="space-y-12">
          {/* Article Header */}
          <div className="space-y-8 text-center border-b border-white/10 pb-12">
            <div className="flex items-center justify-center gap-4">
              {post.tags && post.tags.map(tag => (
                <span key={tag} className="text-[10px] font-bold uppercase tracking-widest text-emerald-500 border border-emerald-900/50 bg-emerald-900/10 px-3 py-1">
                  {tag}
                </span>
              ))}
            </div>
            
            <h1 className="text-4xl md:text-6xl font-bold tracking-tighter leading-none text-white uppercase">
              {post.title}
            </h1>

            <div className="flex items-center justify-center gap-8 text-xs text-zinc-500 font-mono uppercase tracking-wider">
              <span className="flex items-center gap-2">
                <User size={14} />
                {post.author_name || 'System'}
              </span>
              <span className="flex items-center gap-2">
                <Calendar size={14} />
                {formatDate(post.published_at || post.created_at)}
              </span>
            </div>
          </div>

          {/* Cover Image */}
          {post.cover_image && (
            <div className="w-full aspect-[21/9] bg-zinc-900 border border-zinc-800 overflow-hidden relative group">
              <img
                src={post.cover_image}
                alt={post.title}
                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-700 grayscale group-hover:grayscale-0"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-transparent to-transparent opacity-50" />
            </div>
          )}

          {/* Content */}
          <div className="prose prose-invert prose-lg max-w-none prose-headings:font-bold prose-headings:uppercase prose-headings:tracking-tight prose-p:text-zinc-400 prose-p:font-light prose-p:leading-relaxed prose-a:text-white prose-a:no-underline prose-a:border-b prose-a:border-zinc-700 hover:prose-a:border-white prose-blockquote:border-l-white prose-blockquote:text-zinc-300 prose-code:text-emerald-400 prose-code:bg-zinc-900 prose-code:px-1 prose-code:py-0.5 prose-code:rounded-none prose-code:font-mono prose-code:before:content-none prose-code:after:content-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {post.content}
            </ReactMarkdown>
          </div>

          {/* Footer / Share / Like */}
          <div className="pt-12 border-t border-white/10 flex flex-col sm:flex-row justify-between items-center gap-6">
            <Link 
              to="/blog"
              className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors group"
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
              Return to Archive
            </Link>
            
            <div className="flex items-center gap-6">
              <button
                onClick={handleLike}
                className={`inline-flex items-center gap-2 px-4 py-2 border text-xs font-bold uppercase tracking-widest transition-all ${
                  liked 
                    ? 'text-emerald-400 border-emerald-900 bg-emerald-900/10' 
                    : 'text-zinc-500 border-zinc-800 hover:text-white hover:border-zinc-600'
                }`}
              >
                <Heart 
                  className={`w-4 h-4 ${liked ? 'fill-current' : ''}`} 
                />
                <span>{likesCount}</span>
              </button>
              
              <button
                onClick={handleShare}
                className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
              >
                <Share2 className="w-4 h-4" />
                Share Protocol
              </button>
            </div>
          </div>

          {/* Comments Section */}
          <section className="pt-16 max-w-2xl mx-auto">
            <div className="flex items-center gap-3 border-b border-white/10 pb-6 mb-8">
              <MessageSquare className="w-5 h-5 text-zinc-500" />
              <h2 className="text-xl font-bold uppercase tracking-tight text-white">
                Feedback Loop <span className="text-zinc-600 ml-2">({comments.length})</span>
              </h2>
            </div>

            {/* Comment Form */}
            <form onSubmit={handleSubmitComment} className="mb-12 bg-zinc-900/30 p-6 border border-white/5">
              <div className="space-y-6">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2 font-bold">
                    Identification (Optional)
                  </label>
                  <input
                    type="text"
                    value={authorName}
                    onChange={(e) => setAuthorName(e.target.value)}
                    placeholder="ENTER DESIGNATION..."
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors font-mono placeholder-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2 font-bold">
                    Input Data
                  </label>
                  <textarea
                    value={commentContent}
                    onChange={(e) => setCommentContent(e.target.value)}
                    placeholder="TRANSMIT MESSAGE..."
                    required
                    rows={4}
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors font-mono placeholder-zinc-700"
                  />
                </div>
              </div>
              
              <div className="flex items-center justify-end mt-6">
                <button
                  type="submit"
                  disabled={submittingComment || !commentContent.trim()}
                  className="inline-flex items-center gap-2 px-8 py-3 bg-white text-black text-xs font-bold uppercase tracking-widest hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {submittingComment ? 'Transmitting...' : 'Send Transmission'}
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>

              {commentSuccess && (
                <div className="mt-4 p-3 bg-emerald-900/20 border border-emerald-900/50 text-emerald-400 text-xs font-mono uppercase tracking-wide">
                   Transmission received. Pending moderation cycle.
                </div>
              )}
            </form>

            {/* Comments List */}
            <div className="space-y-px bg-zinc-900 border border-zinc-800">
              {comments.length === 0 ? (
                <div className="text-center py-12 text-zinc-600 text-xs font-mono uppercase tracking-widest">
                  No data points available
                </div>
              ) : (
                comments.map((comment) => (
                  <div key={comment.id} className="p-6 bg-zinc-950 border-b border-zinc-900">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-bold text-white uppercase tracking-wider">
                        {comment.author_name || 'Anonymous User'}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-600 uppercase">
                        {new Date(comment.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-400 leading-relaxed font-mono">
                      {comment.content}
                    </p>
                  </div>
                ))
              )}
            </div>
          </section>
        </article>
      </main>

       {/* Footer */}
       <footer className="relative z-10 border-t border-white/10 mt-20 bg-zinc-950 py-12 px-6">
        <div className="container mx-auto max-w-5xl flex flex-col sm:flex-row justify-between items-center gap-6">
          <span className="text-[10px] tracking-[0.3em] text-zinc-600 uppercase">
            © {new Date().getFullYear()} Matcha Intelligence
          </span>
          <div className="flex gap-8">
            <Link to="/" className="text-[10px] tracking-[0.2em] text-zinc-500 hover:text-white uppercase transition-colors">System</Link>
            <Link to="/blog" className="text-[10px] tracking-[0.2em] text-zinc-500 hover:text-white uppercase transition-colors">Archive</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default PublicBlogDetail;
