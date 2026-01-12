import { useEffect, useState } from 'react';
import { blogs } from '../api/client';
import type { BlogComment } from '../types';
import { GlassCard } from '../components/GlassCard';
import { Check, X, MessageSquare, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

export function BlogCommentsAdmin() {
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
      alert('Failed to update comment status');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="w-2 h-2 rounded-full bg-white animate-ping" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-light tracking-tight text-white">Comment Moderation</h1>
        <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Review and approve guest comments
        </p>
      </div>

      {comments.length === 0 ? (
        <GlassCard className="p-16 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-zinc-900/50 border border-zinc-800 flex items-center justify-center">
            <MessageSquare className="w-8 h-8 text-zinc-700" strokeWidth={1.5} />
          </div>
          <h3 className="text-xl font-light text-white mb-2">No pending comments</h3>
          <p className="text-sm text-zinc-500 max-w-sm mx-auto">
            Everything is caught up! New guest comments will appear here for review.
          </p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {comments.map((comment) => (
            <GlassCard key={comment.id} className="p-6">
              <div className="flex flex-col md:flex-row gap-6">
                <div className="flex-1 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <div className="text-sm font-medium text-white flex items-center gap-2">
                        {comment.author_name}
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono uppercase tracking-wider">
                          Guest
                        </span>
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">
                        {new Date(comment.created_at).toLocaleString()}
                      </div>
                    </div>
                    {comment.post_title && (
                      <Link
                        to={`/blog/${comment.post_id}`} // This should ideally be slug, but we'll use ID if slug not available
                        className="flex items-center gap-1.5 text-[10px] text-emerald-500 hover:text-emerald-400 transition-colors uppercase font-medium tracking-wider"
                      >
                        On: {comment.post_title}
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                  
                  <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded-md text-sm text-zinc-300 leading-relaxed italic">
                    "{comment.content}"
                  </div>
                </div>

                <div className="flex md:flex-col justify-end gap-2">
                  <button
                    onClick={() => handleModerate(comment.id, 'approved')}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-900/20 text-emerald-400 border border-emerald-900/50 rounded hover:bg-emerald-900/30 transition-all text-[10px] uppercase tracking-widest font-bold"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleModerate(comment.id, 'rejected')}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-red-900/20 text-red-400 border border-red-900/50 rounded hover:bg-red-900/30 transition-all text-[10px] uppercase tracking-widest font-bold"
                  >
                    <X className="w-3.5 h-3.5" />
                    Reject
                  </button>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}

export default BlogCommentsAdmin;
