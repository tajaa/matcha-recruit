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
      
      // Update document title
      document.title = `${data.meta_title || data.title} | Matcha Blog`;
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
    
    // Optimistic update
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
      // Revert on error
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
      alert('Failed to submit comment. Please try again.');
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
          <div className="prose prose-stone prose-lg max-w-none prose-p:font-serif prose-p:text-zinc-800 prose-p:leading-relaxed prose-headings:font-sans prose-headings:font-light prose-a:text-emerald-600 prose-a:no-underline hover:prose-a:underline">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {post.content}
            </ReactMarkdown>
          </div>

          {/* Footer / Share / Like */}
          <div className="pt-12 border-t border-zinc-200 flex items-center justify-between">
            <Link 
              to="/blog"
              className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-emerald-700 transition-colors group"
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
              Back to Blog
            </Link>
            
            <div className="flex items-center gap-4">
              <button
                onClick={handleLike}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  liked 
                    ? 'text-pink-600 bg-pink-50 border border-pink-200' 
                    : 'text-zinc-500 hover:text-pink-600 hover:bg-pink-50/50 border border-transparent'
                }`}
              >
                <Heart 
                  className={`w-4 h-4 ${liked ? 'fill-current' : ''}`} 
                />
                <span>{likesCount}</span>
              </button>
              
              <button
                onClick={handleShare}
                className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-emerald-700 transition-colors"
              >
                <Share2 className="w-4 h-4" />
                Share
              </button>
            </div>
          </div>

          {/* Comments Section */}
          <section className="pt-12 space-y-8">
            <div className="flex items-center gap-3 border-b border-zinc-200 pb-4">
              <MessageSquare className="w-5 h-5 text-zinc-400" />
              <h2 className="text-xl font-light tracking-tight text-zinc-900">
                Comments ({comments.length})
              </h2>
            </div>

            {/* Comment Form */}
            <form onSubmit={handleSubmitComment} className="space-y-4 bg-white/50 p-6 rounded-lg border border-zinc-200">
              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2 font-medium">
                    Name (optional if logged in)
                  </label>
                  <input
                    type="text"
                    value={authorName}
                    onChange={(e) => setAuthorName(e.target.value)}
                    placeholder="Your name"
                    className="w-full bg-white border border-zinc-200 rounded-md px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2 font-medium">
                    Comment
                  </label>
                  <textarea
                    value={commentContent}
                    onChange={(e) => setCommentContent(e.target.value)}
                    placeholder="Share your thoughts..."
                    required
                    rows={4}
                    className="w-full bg-white border border-zinc-200 rounded-md px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all"
                  />
                </div>
              </div>
              
              <div className="flex items-center justify-between">
                <p className="text-[10px] text-zinc-400 italic">
                  Guest comments will be reviewed by our team before publishing.
                </p>
                <button
                  type="submit"
                  disabled={submittingComment || !commentContent.trim()}
                  className="inline-flex items-center gap-2 px-6 py-2 bg-zinc-900 text-white text-xs font-medium uppercase tracking-widest rounded-md hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {submittingComment ? 'Sending...' : 'Post Comment'}
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>

              {commentSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-100 text-emerald-700 text-xs rounded-md animate-in fade-in slide-in-from-top-2">
                  Thank you! Your comment has been submitted for review.
                </div>
              )}
            </form>

            {/* Comments List */}
            <div className="space-y-6">
              {comments.length === 0 ? (
                <p className="text-center py-8 text-zinc-400 text-sm italic">
                  No comments yet. Be the first to start the conversation!
                </p>
              ) : (
                comments.map((comment) => (
                  <div key={comment.id} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-zinc-900">
                        {comment.author_name}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-400 uppercase">
                        {new Date(comment.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="bg-white/30 border border-zinc-100 p-4 rounded-lg text-sm text-zinc-700 leading-relaxed">
                      {comment.content}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
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