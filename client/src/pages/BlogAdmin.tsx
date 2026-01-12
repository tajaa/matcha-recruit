import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '../components/Button';
import { GlassCard } from '../components/GlassCard';
import { blogs } from '../api/client';
import type { BlogPost, BlogStatus } from '../types';
import { FileText, Filter, PenSquare, Trash2 } from 'lucide-react';

const statusClasses: Record<BlogStatus, string> = {
  draft: 'bg-zinc-800/80 text-zinc-400 border-zinc-700',
  published: 'bg-emerald-900/20 text-emerald-400 border-emerald-900/50',
  archived: 'bg-zinc-800/80 text-zinc-500 border-zinc-700',
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
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<BlogStatus | ''>(initialStatus);

  const loadPosts = useCallback(async (status?: BlogStatus | '') => {
    try {
      setLoading(true);
      const data = await blogs.list({ status: status || undefined, limit: 50 });
      setPosts(data.items);
      setTotal(data.total);
    } catch (error) {
      console.error('Failed to load blog posts:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPosts(statusFilter);
  }, [loadPosts, statusFilter]);

  const handleFilterChange = (value: string) => {
    const nextStatus = value as BlogStatus | '';
    setStatusFilter(nextStatus);
    if (nextStatus) {
      setSearchParams({ status: nextStatus });
    } else {
      setSearchParams({});
    }
  };

  const handleDelete = async (postId: string) => {
    if (!confirm('Delete this blog post? This cannot be undone.')) return;

    try {
      await blogs.delete(postId);
      loadPosts(statusFilter);
    } catch (error) {
      console.error('Failed to delete blog post:', error);
      alert('Failed to delete blog post');
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
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-white">Blog</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Draft, publish, and manage posts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            {total} posts
          </div>
          <Button onClick={() => navigate('/app/blog/new')}>New Post</Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/50 border border-zinc-800 rounded-md">
          <Filter className="w-3.5 h-3.5 text-zinc-500" />
          <select
            value={statusFilter}
            onChange={(event) => handleFilterChange(event.target.value)}
            className="bg-transparent text-zinc-300 text-xs focus:outline-none uppercase tracking-widest font-medium cursor-pointer"
          >
            <option value="">All Posts</option>
            <option value="draft">Drafts</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {posts.length === 0 ? (
        <GlassCard className="p-16 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-zinc-900/50 border border-zinc-800 flex items-center justify-center">
            <FileText className="w-8 h-8 text-zinc-700" strokeWidth={1.5} />
          </div>
          <h3 className="text-xl font-light text-white mb-2">No blog posts yet</h3>
          <p className="text-sm text-zinc-500 mb-8 max-w-sm mx-auto">
            Create your first post to start publishing content.
          </p>
          <Button onClick={() => navigate('/app/blog/new')}>Create Post</Button>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {posts.map((post) => (
            <GlassCard key={post.id} className="group">
              <div className="p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
                <div className="space-y-2">
                  <div className="flex items-center gap-3 flex-wrap">
                    <Link
                      to={`/app/blog/${post.slug}`}
                      className="text-lg font-medium text-white group-hover:text-white transition-colors"
                    >
                      {post.title}
                    </Link>
                    <span
                      className={`px-2.5 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium border ${statusClasses[post.status]}`}
                    >
                      {post.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-600 font-mono tracking-wide">
                    /blog/{post.slug}
                  </div>
                  {post.excerpt && (
                    <p className="text-sm text-zinc-500 max-w-2xl">{post.excerpt}</p>
                  )}
                  <div className="flex flex-wrap gap-4 text-[11px] text-zinc-500 font-mono uppercase tracking-widest">
                    <span>Author: {post.author_name || 'Admin'}</span>
                    <span>Created: {formatDate(post.created_at)}</span>
                    <span>Published: {formatDate(post.published_at)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    to={`/app/blog/${post.slug}`}
                    className="inline-flex items-center gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-400 border border-zinc-800 hover:border-zinc-600 hover:text-zinc-200 transition-colors"
                  >
                    <PenSquare className="w-4 h-4" />
                    Edit
                  </Link>
                  <button
                    type="button"
                    onClick={() => handleDelete(post.id)}
                    className="inline-flex items-center gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-red-400 border border-red-500/30 hover:border-red-500/50 hover:text-red-300 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
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

export default BlogAdmin;
