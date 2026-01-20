import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { policies, getAccessToken } from '../api/client';
import type { PolicyUpdate, PolicyStatus } from '../types';
import { ChevronLeft, FileText, Upload, X } from 'lucide-react';

export function PolicyForm() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isEditing = !!id;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [version, setVersion] = useState('1.0');
  const [status, setStatus] = useState<PolicyStatus>('draft');
  const [loading, setLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (isEditing) {
      loadPolicy(id!);
    }
  }, [id, isEditing]);

  const loadPolicy = async (policyId: string) => {
    try {
      setLoading(true);
      const data = await policies.get(policyId);
      setTitle(data.title);
      setDescription(data.description || '');
      setContent(data.content);
      setVersion(data.version);
      setStatus(data.status);
    } catch (error) {
      console.error('Failed to load policy:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    try {
      setLoading(true);

      if (isEditing) {
        const updateData: PolicyUpdate = {
          title,
          description: description || null,
          content,
          version,
          status,
        };
        await policies.update(id!, updateData);
      } else {
        const formData = new FormData();
        formData.append('title', title);
        formData.append('description', description);
        formData.append('content', content);
        formData.append('version', version);
        formData.append('status', status);
        if (file) {
          formData.append('file', file);
        }
        
        await fetch('/api/policies', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getAccessToken()}`,
          },
          body: formData,
        });
      }

      navigate('/app/matcha/policies');
    } catch (error) {
      console.error('Failed to save policy:', error);
    } finally {
      setLoading(false);
    }
  };

  if (isEditing && !title && loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading policy data...</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="text-xs text-zinc-500 hover:text-white mb-4 flex items-center gap-1 uppercase tracking-wider"
          >
            <ChevronLeft size={12} />
            Back
          </button>
          <h1 className="text-3xl font-light tracking-tight text-white">
            {isEditing ? 'Edit Policy' : 'Create Policy'}
          </h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            {isEditing ? 'Update existing policy documentation' : 'Draft a new company guideline'}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-10">
        <div className="space-y-8">
          {/* Basic Info */}
          <div className="space-y-6">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-white/20 text-white placeholder-zinc-300 text-lg focus:outline-none focus:border-white transition-colors"
                placeholder="e.g. Employee Conduct Policy"
                required
              />
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Short Description</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-white/20 text-white placeholder-zinc-300 text-sm focus:outline-none focus:border-white transition-colors"
                placeholder="Brief summary of the policy purpose"
              />
            </div>
          </div>

          {/* Content */}
          <div className="space-y-4 pt-4">
            <div className="flex items-center justify-between border-b border-white/20 pb-2">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Content</label>
              <span className="text-[9px] text-zinc-400 font-mono italic">Plain text or basic formatting</span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full px-4 py-4 bg-zinc-900 border border-white/20 rounded-sm text-white text-sm font-serif leading-relaxed min-h-[400px] focus:outline-none focus:border-white/40 transition-all resize-none placeholder-zinc-500"
              placeholder="Start drafting policy content here..."
              required
            />
          </div>

          {/* File Upload */}
          <div className="space-y-4 pt-4">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-bold border-b border-white/20 pb-2">
              Reference Document (Optional)
            </label>
            <div className="flex items-center gap-6 p-6 border-2 border-dashed border-white/10 rounded-lg bg-white/5 hover:bg-white/10 transition-colors group">
              <div className="w-12 h-12 rounded-full bg-zinc-900 border border-white/20 flex items-center justify-center text-zinc-400 group-hover:text-white transition-colors">
                <Upload size={20} />
              </div>
              <div className="flex-1">
                <label className="cursor-pointer">
                  <span className="text-sm font-medium text-white hover:underline">Click to upload policy PDF</span>
                  <input
                    type="file"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    accept=".pdf,.doc,.docx,.txt"
                    className="hidden"
                  />
                  <p className="text-xs text-zinc-500 mt-1">Supports PDF, DOC, DOCX up to 10MB</p>
                </label>
              </div>
              {file && (
                <div className="flex items-center gap-3 bg-zinc-900 px-3 py-2 rounded border border-white/20">
                  <FileText size={14} className="text-zinc-400" />
                  <span className="text-xs text-white truncate max-w-[120px]">{file.name}</span>
                  <button onClick={() => setFile(null)} className="text-zinc-400 hover:text-red-600 transition-colors">
                    <X size={14} />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Meta */}
          <div className="grid grid-cols-2 gap-8 pt-4">
            <div className="space-y-2">
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Version</label>
              <input
                type="text"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="w-full px-0 py-2 bg-transparent border-b border-white/20 text-white text-sm focus:outline-none focus:border-white transition-colors font-mono"
                placeholder="1.0"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Publication Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as PolicyStatus)}
                className="w-full px-0 py-2 bg-transparent border-b border-white/20 text-white text-sm focus:outline-none focus:border-white transition-colors cursor-pointer uppercase tracking-wider font-medium"
              >
                <option value="draft">Draft (Private)</option>
                <option value="active">Active (Publish)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex justify-end gap-4 pt-10 border-t border-white/10">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-6 py-2 text-zinc-500 hover:text-white text-xs font-medium uppercase tracking-wider transition-colors"
          >
            Discard
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-8 py-2 bg-white hover:bg-zinc-200 text-black rounded-sm text-xs font-medium uppercase tracking-wider transition-colors disabled:opacity-50"
          >
            {loading ? 'Saving...' : isEditing ? 'Update Policy' : 'Create Policy'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default PolicyForm;