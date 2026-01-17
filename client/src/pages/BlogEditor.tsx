import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { blogs } from '../api/client';
import type { BlogPostCreate, BlogStatus } from '../types';
import { ChevronLeft, X, Upload } from 'lucide-react';

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
      <div className="flex items-center justify-center py-24">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading post data...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-white/10 pb-8">
        <div>
          <button
            onClick={() => navigate('/app/blog')}
            className="text-xs text-zinc-500 hover:text-white mb-4 flex items-center gap-1 uppercase tracking-wider transition-colors"
          >
            <ChevronLeft size={12} />
            Back to Posts
          </button>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">
            {isEditing ? 'Edit Transmission' : 'New Transmission'}
          </h1>
          {publishedAt && (
            <p className="text-[10px] text-zinc-500 font-mono mt-2 uppercase tracking-widest">
              Published on {new Date(publishedAt).toLocaleDateString()}
            </p>
          )}
        </div>
        <div className="w-48">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as BlogStatus)}
            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-xs text-white focus:outline-none focus:border-zinc-600 cursor-pointer uppercase tracking-wider font-bold"
          >
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-12">
        <div className="space-y-8">
          {/* Main Title */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">Post Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => handleTitleChange(e.target.value)}
              className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-white placeholder-zinc-700 text-3xl font-bold tracking-tight focus:outline-none focus:border-white transition-colors"
              placeholder="ENTER TITLE..."
              required
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">URL Slug</label>
              <input
                type="text"
                value={postSlug}
                onChange={(e) => handleSlugChange(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-400 font-mono text-xs focus:outline-none focus:border-zinc-600 transition-colors"
                placeholder="post-url-slug"
                required
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">Tags</label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-300 text-xs font-mono focus:outline-none focus:border-zinc-600 transition-colors"
                placeholder="hiring, culture, leadership"
              />
            </div>
          </div>

          {/* Excerpt */}
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">Excerpt</label>
            <textarea
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-300 text-sm focus:outline-none focus:border-zinc-600 transition-colors resize-none placeholder-zinc-700"
              placeholder="Short summary for preview cards..."
              rows={2}
            />
          </div>

          {/* Content Body */}
          <div className="space-y-4 pt-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-2">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Body Content</label>
              <span className="text-[9px] text-zinc-600 font-mono italic">Markdown Supported</span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full px-6 py-6 bg-zinc-900 border border-zinc-800 text-zinc-300 text-sm font-mono leading-relaxed min-h-[600px] focus:outline-none focus:border-zinc-600 focus:bg-zinc-900 transition-all resize-none shadow-inner placeholder-zinc-700"
              placeholder="Begin writing..."
              required
            />
          </div>

          {/* Cover Image */}
          <div className="space-y-4 pt-4">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-bold border-b border-zinc-800 pb-2">
              Cover Image
            </label>
            <div className="flex flex-col gap-6">
              <div className="flex items-center gap-4">
                <input
                  type="text"
                  value={coverImage}
                  onChange={(e) => setCoverImage(e.target.value)}
                  className="flex-1 px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-300 text-xs font-mono focus:outline-none focus:border-zinc-600 transition-colors placeholder-zinc-700"
                  placeholder="Image URL (https://...)"
                />
                <label className="cursor-pointer flex items-center gap-2 px-4 py-2 bg-zinc-900 border border-zinc-700 text-zinc-400 text-[10px] font-bold uppercase tracking-wider hover:bg-zinc-800 hover:text-white transition-colors">
                  <Upload size={14} />
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
                <div className="relative group w-full aspect-video max-h-[300px] overflow-hidden border border-zinc-800 bg-zinc-900">
                  <img src={coverImage} alt="Cover" className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
                  <button 
                    onClick={() => setCoverImage('')}
                    type="button"
                    className="absolute top-2 right-2 p-2 bg-black/80 text-white hover:bg-red-900 transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* SEO Metadata */}
          <div className="space-y-6 pt-12 border-t border-white/5">
            <h3 className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold flex items-center gap-2">
               SEO Configuration
            </h3>
            <div className="space-y-6 bg-zinc-900/30 p-6 border border-white/5">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">Meta Title</label>
                <input
                  type="text"
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-300 text-xs focus:outline-none focus:border-zinc-600 transition-colors placeholder-zinc-700"
                  placeholder="SEO Search Title"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2 font-bold">Meta Description</label>
                <textarea
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-zinc-300 text-xs focus:outline-none focus:border-zinc-600 transition-colors resize-none placeholder-zinc-700"
                  placeholder="SEO Search Description"
                  rows={2}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex justify-end gap-4 pt-10 border-t border-white/10 pb-20">
          <button
            type="button"
            onClick={() => navigate('/app/blog')}
            className="px-6 py-3 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors border border-transparent hover:border-zinc-800"
          >
            Discard Changes
          </button>
          <button 
            type="submit" 
            disabled={saving}
            className="px-8 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-widest transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : isEditing ? 'Update Transmission' : 'Create Transmission'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default BlogEditor;
