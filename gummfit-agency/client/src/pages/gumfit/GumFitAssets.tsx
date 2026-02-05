import { useEffect, useState, useRef } from 'react';
import { Search, Upload, Trash2, Edit2, Copy, Check, X, Image, Filter } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitAsset, GumFitAssetCategory } from '../../api/client';

export function GumFitAssets() {
  const [assets, setAssets] = useState<GumFitAsset[]>([]);
  const [categories, setCategories] = useState<GumFitAssetCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [editingAsset, setEditingAsset] = useState<GumFitAsset | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload form state
  const [uploadName, setUploadName] = useState('');
  const [uploadCategory, setUploadCategory] = useState('general');
  const [uploadAltText, setUploadAltText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    loadAssets();
  }, [search, categoryFilter]);

  const loadCategories = async () => {
    try {
      const res = await api.gumfit.listAssetCategories();
      setCategories(res.categories);
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  };

  const loadAssets = async () => {
    try {
      const res = await api.gumfit.listAssets({
        search: search || undefined,
        category: categoryFilter || undefined,
      });
      setAssets(res.assets);
    } catch (err) {
      console.error('Failed to load assets:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setUploadName(file.name.replace(/\.[^/.]+$/, ''));
      setPreviewUrl(URL.createObjectURL(file));
      setShowUploadModal(true);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || !uploadName) return;

    setUploading(true);
    try {
      const newAsset = await api.gumfit.uploadAsset(
        selectedFile,
        uploadName,
        uploadCategory,
        uploadAltText || undefined
      );
      setAssets([newAsset, ...assets]);
      closeUploadModal();
    } catch (err) {
      console.error('Failed to upload asset:', err);
    } finally {
      setUploading(false);
    }
  };

  const closeUploadModal = () => {
    setShowUploadModal(false);
    setSelectedFile(null);
    setPreviewUrl(null);
    setUploadName('');
    setUploadCategory('general');
    setUploadAltText('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (assetId: string) => {
    if (!confirm('Are you sure you want to delete this asset?')) return;

    try {
      await api.gumfit.deleteAsset(assetId);
      setAssets(assets.filter((a) => a.id !== assetId));
    } catch (err) {
      console.error('Failed to delete asset:', err);
    }
  };

  const handleUpdate = async () => {
    if (!editingAsset) return;

    try {
      const updated = await api.gumfit.updateAsset(editingAsset.id, {
        name: editingAsset.name,
        category: editingAsset.category,
        alt_text: editingAsset.alt_text ?? undefined,
      });
      setAssets(assets.map((a) => (a.id === updated.id ? updated : a)));
      setEditingAsset(null);
    } catch (err) {
      console.error('Failed to update asset:', err);
    }
  };

  const copyUrl = async (url: string, id: string) => {
    await navigator.clipboard.writeText(url);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return 'Unknown';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
            GumFit Admin
          </div>
          <h1 className="text-2xl font-bold text-white">Assets</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Manage marketing images for landing pages
          </p>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-4 py-2 bg-white text-black text-sm font-medium hover:bg-zinc-200 transition-colors"
        >
          <Upload className="w-4 h-4" />
          Upload Asset
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search assets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="pl-10 pr-8 py-2 bg-zinc-900 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30 appearance-none cursor-pointer"
          >
            <option value="">All Categories</option>
            {categories.map((cat) => (
              <option key={cat.value} value={cat.value}>
                {cat.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Assets Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {assets.map((asset) => (
          <div
            key={asset.id}
            className="border border-white/10 bg-zinc-900/30 group hover:border-white/20 transition-colors"
          >
            {/* Image Preview */}
            <div className="aspect-square relative overflow-hidden bg-zinc-800">
              {asset.url ? (
                <img
                  src={asset.url}
                  alt={asset.alt_text || asset.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Image className="w-8 h-8 text-zinc-600" />
                </div>
              )}
              {/* Overlay Actions */}
              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                <button
                  onClick={() => copyUrl(asset.url, asset.id)}
                  className="p-2 bg-white/10 hover:bg-white/20 transition-colors"
                  title="Copy URL"
                >
                  {copiedId === asset.id ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-white" />
                  )}
                </button>
                <button
                  onClick={() => setEditingAsset(asset)}
                  className="p-2 bg-white/10 hover:bg-white/20 transition-colors"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4 text-white" />
                </button>
                <button
                  onClick={() => handleDelete(asset.id)}
                  className="p-2 bg-white/10 hover:bg-red-500/50 transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4 text-white" />
                </button>
              </div>
            </div>
            {/* Info */}
            <div className="p-3">
              <div className="text-sm text-white font-medium truncate" title={asset.name}>
                {asset.name}
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500">
                  {asset.category}
                </span>
                <span className="text-[10px] text-zinc-500">
                  {formatFileSize(asset.file_size)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {assets.length === 0 && (
        <div className="text-center py-12 border border-white/10 bg-zinc-900/30">
          <Image className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
          <p className="text-zinc-500 text-sm">No assets found</p>
          <p className="text-zinc-600 text-xs mt-1">Upload your first asset to get started</p>
        </div>
      )}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-lg">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Upload Asset</h2>
              <button
                onClick={closeUploadModal}
                className="p-1 text-zinc-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              {/* Preview */}
              {previewUrl && (
                <div className="aspect-video bg-zinc-800 overflow-hidden">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="w-full h-full object-contain"
                  />
                </div>
              )}
              {/* Name */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Name
                </label>
                <input
                  type="text"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30"
                />
              </div>
              {/* Category */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Category
                </label>
                <select
                  value={uploadCategory}
                  onChange={(e) => setUploadCategory(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30"
                >
                  {categories.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>
              {/* Alt Text */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Alt Text (optional)
                </label>
                <input
                  type="text"
                  value={uploadAltText}
                  onChange={(e) => setUploadAltText(e.target.value)}
                  placeholder="Describe the image for accessibility"
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white/30"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-white/10">
              <button
                onClick={closeUploadModal}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={uploading || !uploadName || !selectedFile}
                className="px-4 py-2 bg-white text-black text-sm font-medium hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingAsset && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-lg">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Edit Asset</h2>
              <button
                onClick={() => setEditingAsset(null)}
                className="p-1 text-zinc-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              {/* Preview */}
              <div className="aspect-video bg-zinc-800 overflow-hidden">
                <img
                  src={editingAsset.url}
                  alt={editingAsset.alt_text || editingAsset.name}
                  className="w-full h-full object-contain"
                />
              </div>
              {/* Name */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Name
                </label>
                <input
                  type="text"
                  value={editingAsset.name}
                  onChange={(e) =>
                    setEditingAsset({ ...editingAsset, name: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30"
                />
              </div>
              {/* Category */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Category
                </label>
                <select
                  value={editingAsset.category}
                  onChange={(e) =>
                    setEditingAsset({ ...editingAsset, category: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30"
                >
                  {categories.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>
              {/* Alt Text */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Alt Text
                </label>
                <input
                  type="text"
                  value={editingAsset.alt_text || ''}
                  onChange={(e) =>
                    setEditingAsset({ ...editingAsset, alt_text: e.target.value })
                  }
                  placeholder="Describe the image for accessibility"
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white/30"
                />
              </div>
              {/* URL (readonly) */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  URL
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={editingAsset.url}
                    readOnly
                    className="flex-1 px-3 py-2 bg-zinc-800/50 border border-white/5 text-zinc-400 text-sm"
                  />
                  <button
                    onClick={() => copyUrl(editingAsset.url, editingAsset.id)}
                    className="px-3 py-2 bg-zinc-800 border border-white/10 text-white hover:bg-zinc-700 transition-colors"
                  >
                    {copiedId === editingAsset.id ? (
                      <Check className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-white/10">
              <button
                onClick={() => setEditingAsset(null)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUpdate}
                className="px-4 py-2 bg-white text-black text-sm font-medium hover:bg-zinc-200 transition-colors"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default GumFitAssets;
