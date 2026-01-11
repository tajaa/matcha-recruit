import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { blogs } from '../api/client';
import type { BlogPostCreate, BlogStatus } from '../types';

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
        alert('Failed to load blog post');
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

  const buildPayload = (overrideStatus?: BlogStatus): BlogPostCreate => {
    const trimmedTitle = title.trim();
    const trimmedSlug = postSlug.trim() || slugify(trimmedTitle);
    const trimmedExcerpt = excerpt.trim();
    const trimmedContent = content.trim();
    const trimmedMetaTitle = metaTitle.trim();
    const trimmedMetaDescription = metaDescription.trim();
    const trimmedCover = coverImage.trim();

    return {
      title: trimmedTitle,
      slug: trimmedSlug,
      content: trimmedContent,
      status: overrideStatus || status,
      excerpt: trimmedExcerpt || null,
      cover_image: trimmedCover || null,
      tags: parseTags(tags),
      meta_title: trimmedMetaTitle || null,
      meta_description: trimmedMetaDescription || null,
    };
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const trimmedContent = content.trim();
    const finalSlug = postSlug.trim() || slugify(trimmedTitle);

    if (!trimmedTitle) {
      alert('Title is required.');
      return;
    }
    if (!finalSlug) {
      alert('Slug is required.');
      return;
    }
    if (!trimmedContent) {
      alert('Content is required.');
      return;
    }

    try {
      setSaving(true);
      const payload = buildPayload();
      if (isEditing && postId) {
        const updated = await blogs.update(postId, payload);
        setPostSlug(updated.slug);
        setStatus(updated.status);
        setPublishedAt(updated.published_at || null);
        navigate(`/app/blog/${updated.slug}`);
      } else {
        const created = await blogs.create(payload);
        navigate(`/app/blog/${created.slug}`);
      }
    } catch (error) {
      console.error('Failed to save blog post:', error);
      alert('Failed to save blog post');
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
      alert('Failed to upload image');
    } finally {
      setUploading(false);
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
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            {isEditing ? 'Edit Blog Post' : 'Create Blog Post'}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {isEditing ? 'Update and publish your content.' : 'Draft a new story for your audience.'}
          </p>
        </div>
        {publishedAt && (
          <div className="text-xs text-zinc-500 font-mono uppercase tracking-widest">
            Published {new Date(publishedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <div className="p-6 space-y-5">
            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(event) => handleTitleChange(event.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                placeholder="Post title"
                required
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Slug *
                </label>
                <input
                  type="text"
                  value={postSlug}
                  onChange={(event) => handleSlugChange(event.target.value)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                  placeholder="blog-post-title"
                  required
                />
                <p className="text-[10px] text-zinc-600 mt-1">
                  Used for the URL. Keep it short and lowercase.
                </p>
              </div>
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Status
                </label>
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value as BlogStatus)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Excerpt
              </label>
              <textarea
                value={excerpt}
                onChange={(event) => setExcerpt(event.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md min-h-[80px]"
                placeholder="Short summary for previews"
              />
            </div>

            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Content *
              </label>
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md min-h-[300px] font-mono text-xs leading-relaxed"
                placeholder="Write your blog post content..."
                required
              />
              <p className="text-[10px] text-zinc-600 mt-1">
                Supports rich text or markdown if your renderer allows it.
              </p>
            </div>

            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Tags
              </label>
              <input
                type="text"
                value={tags}
                onChange={(event) => setTags(event.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                placeholder="hiring, culture, leadership"
              />
              <p className="text-[10px] text-zinc-600 mt-1">Separate tags with commas.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
              <div className="md:col-span-2">
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Cover Image URL
                </label>
                <input
                  type="text"
                  value={coverImage}
                  onChange={(event) => setCoverImage(event.target.value)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                  placeholder="https://..."
                />
              </div>
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Upload Image
                </label>
                <label className="cursor-pointer w-full inline-flex items-center justify-center px-4 py-2 bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs uppercase tracking-widest rounded-md hover:bg-zinc-700 hover:text-white transition-colors">
                  {uploading ? 'Uploading...' : 'Choose File'}
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
            </div>

            {coverImage && (
              <div className="border border-zinc-800 rounded-md p-3 bg-zinc-950/50">
                <img
                  src={coverImage}
                  alt="Cover preview"
                  className="w-full max-h-[220px] object-cover rounded"
                />
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Meta Title
                </label>
                <input
                  type="text"
                  value={metaTitle}
                  onChange={(event) => setMetaTitle(event.target.value)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                  placeholder="SEO title"
                />
              </div>
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Meta Description
                </label>
                <textarea
                  value={metaDescription}
                  onChange={(event) => setMetaDescription(event.target.value)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md min-h-[90px]"
                  placeholder="SEO description"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800">
              <Button
                variant="secondary"
                type="button"
                onClick={() => navigate('/app/blog')}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving...' : isEditing ? 'Update Post' : 'Create Post'}
              </Button>
            </div>
          </div>
        </Card>
      </form>
    </div>
  );
}

export default BlogEditor;
