import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPostCreate, BlogStatus } from '../types';
import { ChevronLeft, X } from 'lucide-react';

const slugify = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const statusOptions: { value: BlogStatus; label: string }[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'published', label: 'Published' },
  { value: 'archived', label: 'Archived' },
];

export function BlogEditor() {
  const { slug } = useParams<{ slug?: string }>();
  const navigate = useNavigate();
  const isEditing = !!slug;

  const [postId, setPostId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [postSlug, setPostSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [status, setStatus] = useState<BlogStatus>('draft');
  const [excerpt, setExcerpt] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [coverImage, setCoverImage] = useState('');
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [publishedAt, setPublishedAt] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!slug) return;

    const loadPost = async () => {
      try {
        setLoading(true);
        const data = await blogs.get(slug);
        setPostId(data.id);
        setTitle(data.title);
        setPostSlug(data.slug);
        setSlugTouched(true);
        setStatus(data.status);
        setExcerpt(data.excerpt || '');
        setContent(data.content);
        setTags(data.tags?.join(', ') || '');
        setCoverImage(data.cover_image || '');
        setMetaTitle(data.meta_title || '');
        setMetaDescription(data.meta_description || '');
        setPublishedAt(data.published_at || null);
      } catch (error) {
        console.error('Failed to load blog post:', error);
      } finally {
        setLoading(false);
      }
    };

    loadPost();
  }, [slug]);

  const handleTitleChange = (value: string) => {
    setTitle(value);
    if (!slugTouched) {
      setPostSlug(slugify(value));
    }
  };

  const handleSlugChange = (value: string) => {
    setPostSlug(value);
    setSlugTouched(true);
  };

  const parseTags = (value: string) =>
    value
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);

  const buildPayload = (overrideStatus?: BlogStatus): BlogPostCreate => ({
    title: title.trim(),
    slug: postSlug.trim() || slugify(title.trim()),
    content: content.trim(),
    status: overrideStatus || status,
    excerpt: excerpt.trim() || null,
    cover_image: coverImage.trim() || null,
    tags: parseTags(tags),
    meta_title: metaTitle.trim() || null,
    meta_description: metaDescription.trim() || null,
  });

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !content.trim()) return;

    try {
      setSaving(true);
      const payload = buildPayload();
      if (isEditing && postId) {
        const updated = await blogs.update(postId, payload);
        navigate(`/app/blog/${updated.slug}`);
      } else {
        const created = await blogs.create(payload);
        navigate(`/app/blog/${created.slug}`);
      }
    } catch (error) {
      console.error('Failed to save blog post:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleUploadCover = async (file: File) => {
    try {
      setUploading(true);
      const result = await blogs.uploadImage(file);
      setCoverImage(result.url);
    } catch (error) {
      console.error('Failed to upload cover image:', error);
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading post data...</div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/app/blog')}
            className="text-xs text-zinc-500 hover:text-zinc-900 mb-4 flex items-center gap-1 uppercase tracking-wider transition-colors"
          >
            <ChevronLeft size={12} />
            Back to Posts
          </button>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">
            {isEditing ? 'Edit Post' : 'New Post'}
          </h1>
          {publishedAt && (
            <p className="text-[10px] text-zinc-400 font-mono mt-2 uppercase tracking-widest">
              Published on {new Date(publishedAt).toLocaleDateString()}
            </p>
          )}
        </div>
        <div className="w-40">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as BlogStatus)}
            className="w-full px-2 py-1.5 bg-transparent border-b border-zinc-200 text-xs text-zinc-600 focus:outline-none focus:border-zinc-400 cursor-pointer uppercase tracking-wider font-medium"
          >
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-10">
        <div className="space-y-8">
          {/* Main Title */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Post Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => handleTitleChange(e.target.value)}
              className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 placeholder-zinc-300 text-2xl font-light focus:outline-none focus:border-zinc-900 transition-colors"
              placeholder="Enter title..."
              required
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">URL Slug</label>
              <input
                type="text"
                value={postSlug}
                onChange={(e) => handleSlugChange(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 font-mono text-xs focus:outline-none focus:border-zinc-900 transition-colors"
                placeholder="post-url-slug"
                required
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Tags</label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 text-xs focus:outline-none focus:border-zinc-900 transition-colors"
                placeholder="hiring, culture, leadership"
              />
            </div>
          </div>

          {/* Excerpt */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Excerpt</label>
            <textarea
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-700 text-sm focus:outline-none focus:border-zinc-900 transition-colors resize-none"
              placeholder="Short summary for preview cards..."
              rows={2}
            />
          </div>

          {/* Content Body */}
          <div className="space-y-4 pt-4">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-2">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Body Content</label>
              <span className="text-[9px] text-zinc-400 font-mono italic">Markdown supported</span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full px-4 py-4 bg-zinc-50 border border-zinc-200 rounded-sm text-zinc-800 text-sm font-serif leading-relaxed min-h-[500px] focus:outline-none focus:border-zinc-400 focus:bg-white transition-all resize-none shadow-inner"
              placeholder="Begin writing..."
              required
            />
          </div>

          {/* Cover Image */}
          <div className="space-y-4 pt-4">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-bold border-b border-zinc-200 pb-2">
              Cover Image
            </label>
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <input
                  type="text"
                  value={coverImage}
                  onChange={(e) => setCoverImage(e.target.value)}
                  className="flex-1 px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 text-xs focus:outline-none focus:border-zinc-900 transition-colors"
                  placeholder="Image URL (https://...)"
                />
                <label className="cursor-pointer px-4 py-2 bg-zinc-100 border border-zinc-200 text-zinc-600 text-[10px] font-bold uppercase tracking-wider rounded-sm hover:bg-zinc-200 transition-colors">
                  {uploading ? 'Uploading...' : 'Upload'}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) handleUploadCover(file);
                    }}
                    disabled={uploading}
                  />
                </label>
              </div>
              {coverImage && (
                <div className="relative group w-full aspect-video max-h-[300px] overflow-hidden rounded border border-zinc-200 bg-zinc-50">
                  <img src={coverImage} alt="Cover" className="w-full h-full object-cover" />
                  <button 
                    onClick={() => setCoverImage('')}
                    type="button"
                    className="absolute top-2 right-2 p-1.5 bg-black/50 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* SEO Metadata */}
          <div className="space-y-6 pt-8 border-t border-zinc-100">
            <h3 className="text-[10px] uppercase tracking-widest text-zinc-400 font-bold">SEO Metadata</h3>
            <div className="space-y-6">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Meta Title</label>
                <input
                  type="text"
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 text-xs focus:outline-none focus:border-zinc-900 transition-colors"
                  placeholder="SEO Search Title"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Meta Description</label>
                <textarea
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-700 text-xs focus:outline-none focus:border-zinc-900 transition-colors resize-none"
                  placeholder="SEO Search Description"
                  rows={2}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex justify-end gap-4 pt-10 border-t border-zinc-100">
          <button
            type="button"
            onClick={() => navigate('/app/blog')}
            className="px-6 py-2 text-zinc-500 hover:text-zinc-900 text-xs font-medium uppercase tracking-wider transition-colors"
          >
            Discard
          </button>
          <button 
            type="submit" 
            disabled={saving}
            className="px-8 py-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded-sm text-xs font-medium uppercase tracking-wider transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : isEditing ? 'Update Post' : 'Create Post'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default BlogEditor;