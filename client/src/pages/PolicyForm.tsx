import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { policies } from '../api/client';
import type { Policy, PolicyCreate as PolicyCreateType, PolicyUpdate } from '../types';

export function PolicyForm() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isEditing = !!id;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState('1.0');
  const [status, setStatus] = useState<'draft' | 'active'>('draft');
  const [loading, setLoading] = useState(false);

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
      alert('Failed to load policy');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      alert('Please enter a title');
      return;
    }

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
        const createData: PolicyCreateType = {
          title,
          description: description || null,
          content,
          version,
          status,
        };
        await policies.create(createData);
      }

      navigate('/app/policies');
    } catch (error) {
      console.error('Failed to save policy:', error);
      alert('Failed to save policy');
    } finally {
      setLoading(false);
    }
  };

  if (isEditing && !title) {
    loadPolicy(id!);
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            {isEditing ? 'Edit Policy' : 'Create Policy'}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {isEditing ? 'Update policy details' : 'Create a new policy document'}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <div className="p-6 space-y-4">
            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                placeholder="Enter policy title"
                required
              />
            </div>

            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md min-h-[80px]"
                placeholder="Brief description of this policy"
              />
            </div>

            <div>
              <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                Content *
              </label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md min-h-[300px] font-mono text-xs leading-relaxed"
                placeholder="Enter policy content..."
                required
              />
              <p className="text-[10px] text-zinc-600 mt-1">
                Tip: You can use basic text formatting. For rich text, paste formatted HTML.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Version
                </label>
                <input
                  type="text"
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                  placeholder="1.0"
                />
              </div>

              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Status
                </label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value as 'draft' | 'active')}
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                >
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800">
              <Button
                variant="secondary"
                type="button"
                onClick={() => navigate(-1)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Saving...' : isEditing ? 'Update Policy' : 'Create Policy'}
              </Button>
            </div>
          </div>
        </Card>
      </form>
    </div>
  );
}

export default PolicyForm;
