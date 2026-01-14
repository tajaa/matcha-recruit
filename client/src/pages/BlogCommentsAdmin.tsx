import { useEffect, useState } from 'react';
import { blogs } from '../api/client';
import type { BlogComment } from '../types';
import { X, ExternalLink, ChevronLeft } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

export function BlogCommentsAdmin() {
  const navigate = useNavigate();
  const [comments, setComments] = useState<BlogComment[]>([]);
  const [loading, setLoading] = useState(true);

  const loadPending = async () => {
    try {
      setLoading(true);
      const data = await blogs.listPendingComments();
      setComments(data);
    } catch (error) {
      console.error('Failed to load pending comments:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPending();
  }, []);

  const handleModerate = async (id: string, status: 'approved' | 'rejected') => {
    try {
      await blogs.moderateComment(id, status);
      setComments(comments.filter(c => c.id !== id));
    } catch (error) {
      console.error('Failed to moderate comment:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading comments...</div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate('/app/blog')}
          className="text-xs text-zinc-500 hover:text-zinc-900 mb-4 flex items-center gap-1 uppercase tracking-wider transition-colors"
        >
          <ChevronLeft size={12} />
          Back to Blog
        </button>
        <h1 className="text-3xl font-light tracking-tight text-zinc-900">Comment Moderation</h1>
        <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Review and approve guest contributions
        </p>
      </div>

      {comments.length === 0 ? (
        <div className="text-center py-16 border-t border-zinc-200">
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-widest">Everything is clean</div>
          <p className="text-sm text-zinc-400 max-w-sm mx-auto">
            New guest comments will appear here for review.
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {/* List Header */}
          <div className="flex items-center gap-4 py-2 text-[10px] text-zinc-500 uppercase tracking-wider border-b border-zinc-200">
            <div className="flex-1">Comment Detail</div>
            <div className="w-48">Post</div>
            <div className="w-40 text-right">Actions</div>
          </div>

          {comments.map((comment) => (
            <div key={comment.id} className="py-6 border-b border-zinc-100 group">
              <div className="flex flex-col md:flex-row gap-8 items-start">
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-zinc-900">{comment.author_name}</span>
                    <span className="text-[10px] text-zinc-400 font-mono">
                      {new Date(comment.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  
                  <div className="text-sm text-zinc-600 leading-relaxed font-serif pl-4 border-l border-zinc-200">
                    "{comment.content}"
                  </div>
                </div>

                <div className="w-48 shrink-0">
                  {comment.post_title && (
                    <Link
                      to={`/app/blog/${comment.post_id}`}
                      className="inline-flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-zinc-900 transition-colors uppercase font-medium tracking-wider"
                    >
                      {comment.post_title}
                      <ExternalLink size={10} />
                    </Link>
                  )}
                </div>

                <div className="w-40 flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handleModerate(comment.id, 'rejected')}
                    className="p-2 text-zinc-400 hover:text-red-600 transition-colors"
                    title="Reject"
                  >
                    <X size={16} />
                  </button>
                  <button
                    onClick={() => handleModerate(comment.id, 'approved')}
                    className="px-4 py-1.5 bg-zinc-900 text-white text-[10px] font-bold uppercase tracking-widest rounded-sm hover:bg-zinc-800 transition-colors"
                  >
                    Approve
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default BlogCommentsAdmin;
