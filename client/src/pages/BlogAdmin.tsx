import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPost, BlogStatus } from '../types';
import { ChevronRight, MessageSquare, Trash2 } from 'lucide-react';

const statusColors: Record<BlogStatus, string> = {
  draft: 'text-zinc-500',
  published: 'text-emerald-500 font-medium',
  archived: 'text-zinc-600',
};

const statusDotColors: Record<BlogStatus, string> = {
  draft: 'bg-zinc-600',
  published: 'bg-emerald-500',
  archived: 'bg-zinc-800',
};

const formatDate = (value: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

export function BlogAdmin() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialStatus = (searchParams.get('status') as BlogStatus) || '';

  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<BlogStatus | ''>(initialStatus);

  const loadPosts = useCallback(async (status?: BlogStatus | '') => {
    try {
      setLoading(true);
      const data = await blogs.list({ status: status || undefined, limit: 50 });
      setPosts(data.items);
    } catch (error) {
      console.error('Failed to load blog posts:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPosts(statusFilter);
  }, [loadPosts, statusFilter]);

  const handleFilterChange = (status: BlogStatus | '') => {
    setStatusFilter(status);
    if (status) {
      setSearchParams({ status });
    } else {
      setSearchParams({});
    }
  };

  const handleDelete = async (e: React.MouseEvent, postId: string) => {
    e.stopPropagation();
    if (!confirm('Delete this blog post? This cannot be undone.')) return;

    try {
      await blogs.delete(postId);
      loadPosts(statusFilter);
    } catch (error) {
      console.error('Failed to delete blog post:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading posts...</div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Blog Management</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Draft, publish, and manage content
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Link
            to="/app/blog/comments"
            className="text-[10px] text-zinc-400 hover:text-white uppercase tracking-wider font-medium flex items-center gap-1.5 transition-colors border border-white/10 px-3 py-2 hover:border-white/30"
          >
            <MessageSquare size={14} />
            Comments
          </Link>
          <button
            onClick={() => navigate('/app/blog/new')}
            className="px-6 py-2 bg-white text-black text-xs font-bold hover:bg-zinc-200 uppercase tracking-wider transition-colors"
          >
            New Post
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-8 border-b border-white/10 pb-px">
        {[
          { label: 'All', value: '' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Published', value: 'published' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.label}
            onClick={() => handleFilterChange(tab.value as BlogStatus | '')}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              statusFilter === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {posts.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">NO POSTS FOUND</div>
          <button
            onClick={() => navigate('/app/blog/new')}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create your first post
          </button>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10">
          {/* List Header */}
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
            <div className="w-4"></div>
            <div className="flex-1">Title</div>
            <div className="w-32">Status</div>
            <div className="w-24 text-right">Published</div>
            <div className="w-12"></div>
          </div>

          {posts.map((post) => (
            <div 
              key={post.id} 
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
              onClick={() => navigate(`/app/blog/${post.slug}`)}
            >
              <div className="w-4 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[post.status] || 'bg-zinc-700'}`} />
              </div>
              
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300 transition-colors">
                  {post.title}
                </h3>
                <p className="text-[10px] text-zinc-500 font-mono mt-1">/blog/{post.slug}</p>
              </div>

              <div className={`w-32 text-[10px] font-bold uppercase tracking-wider ${statusColors[post.status]}`}>
                {post.status}
              </div>

              <div className="w-24 text-right text-[10px] text-zinc-500 font-mono">
                {formatDate(post.published_at || post.created_at)}
              </div>
              
              <div className="w-12 flex justify-end gap-2">
                <button
                  onClick={(e) => handleDelete(e, post.id)}
                  className="p-1.5 text-zinc-600 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                  title="Delete Post"
                >
                  <Trash2 size={14} />
                </button>
                <ChevronRight size={14} className="text-zinc-700 group-hover:text-white transition-colors" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default BlogAdmin;
