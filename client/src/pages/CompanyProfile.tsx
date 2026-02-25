import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building, Upload, Check, AlertTriangle, MapPin, Settings } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getAccessToken, provisioning } from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';
import type { ClientProfile, GoogleWorkspaceConnectionStatus } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const INDUSTRIES = [
  'Technology', 'Healthcare', 'Finance', 'Education', 'Retail',
  'Manufacturing', 'Construction', 'Hospitality', 'Transportation',
  'Real Estate', 'Legal', 'Media', 'Nonprofit', 'Government', 'Other',
];

const SIZES = [
  { value: 'startup', label: '1-50 employees' },
  { value: 'mid', label: '51-500 employees' },
  { value: 'enterprise', label: '500+ employees' },
];

interface CompanyData {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  logo_url: string | null;
}

function getGoogleBadge(status: GoogleWorkspaceConnectionStatus | null, loading: boolean) {
  if (loading) {
    return { label: 'Checking', tone: 'border-zinc-700 bg-zinc-900/70 text-zinc-300' };
  }
  if (!status || status.status === 'disconnected') {
    return { label: 'Not Connected', tone: 'border-zinc-700 bg-zinc-900/70 text-zinc-300' };
  }
  if (status.status === 'connected') {
    return { label: 'Connected', tone: 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200' };
  }
  if (status.status === 'error') {
    return { label: 'Needs Attention', tone: 'border-red-500/40 bg-red-950/30 text-red-200' };
  }
  return { label: status.status.toUpperCase(), tone: 'border-amber-500/40 bg-amber-950/30 text-amber-200' };
}

export function CompanyProfile() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const clientProfile = profile as ClientProfile | null;
  const companyId = clientProfile?.company_id;

  const [company, setCompany] = useState<CompanyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState<string | null>(null);

  // Form fields
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('');
  const [size, setSize] = useState('');

  // Logo upload
  const [logoUploading, setLogoUploading] = useState(false);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!companyId) {
      setLoading(false);
      return;
    }
    fetchCompany();
  }, [companyId]);

  useEffect(() => {
    if (!companyId) {
      setLoadingGoogle(false);
      return;
    }

    let mounted = true;
    const loadGoogleStatus = async () => {
      setLoadingGoogle(true);
      setGoogleStatusError(null);
      try {
        const status = await provisioning.getGoogleWorkspaceStatus();
        if (mounted) {
          setGoogleStatus(status);
        }
      } catch (err) {
        if (!mounted) return;
        setGoogleStatusError(err instanceof Error ? err.message : 'Could not load Google status');
      } finally {
        if (mounted) {
          setLoadingGoogle(false);
        }
      }
    };

    loadGoogleStatus();
    return () => {
      mounted = false;
    };
  }, [companyId]);

  const fetchCompany = async () => {
    try {
      const token = getAccessToken();
      const res = await fetch(`${API_BASE}/companies/${companyId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to load company');
      const data = await res.json();
      setCompany(data);
      setName(data.name || '');
      setIndustry(data.industry || '');
      setSize(data.size || '');
      setLogoPreview(data.logo_url || null);
    } catch (err) {
      setError('Failed to load company profile');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!companyId) return;
    setSaving(true);
    setError(null);
    setSaveSuccess(false);

    try {
      const token = getAccessToken();
      const body: Record<string, string> = {};
      if (name !== (company?.name || '')) body.name = name;
      if (industry !== (company?.industry || '')) body.industry = industry;
      if (size !== (company?.size || '')) body.size = size;

      if (Object.keys(body).length === 0) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2000);
        setSaving(false);
        return;
      }

      const res = await fetch(`${API_BASE}/companies/${companyId}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || 'Failed to save');
      }

      const updated = await res.json();
      setCompany(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err: any) {
      setError(err.message || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !companyId) return;

    if (!file.type.startsWith('image/')) {
      setError('Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('File size must be under 5MB');
      return;
    }

    setLogoUploading(true);
    setError(null);

    // Show preview immediately
    const reader = new FileReader();
    reader.onload = (ev) => setLogoPreview(ev.target?.result as string);
    reader.readAsDataURL(file);

    try {
      const token = getAccessToken();
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}/companies/${companyId}/logo`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || 'Failed to upload logo');
      }

      const { url } = await res.json();
      setLogoPreview(url);
      setCompany((prev) => prev ? { ...prev, logo_url: url } : prev);
    } catch (err: any) {
      setError(err.message || 'Failed to upload logo');
      // Revert preview on error
      setLogoPreview(company?.logo_url || null);
    } finally {
      setLogoUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const hasChanges =
    name !== (company?.name || '') ||
    industry !== (company?.industry || '') ||
    size !== (company?.size || '');
  const googleBadge = getGoogleBadge(googleStatus, loadingGoogle);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div className="text-center sm:text-left">
          <div className="flex items-center gap-3 mb-2 justify-center sm:justify-start">
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Company Profile
            </div>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tighter text-white uppercase break-all">
            {company?.name || 'Company'}
          </h1>
        </div>
        <div className="flex justify-center sm:justify-end" data-tour="company-setup-guide">
          <FeatureGuideTrigger guideId="company-setup" />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300 text-xs uppercase tracking-wider">
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Company Info */}
        <div className="lg:col-span-2 space-y-8">
          <div data-tour="company-info-form" className="border border-white/10 bg-zinc-900/30">
            <div className="p-6 border-b border-white/10 flex items-center gap-3">
              <Building className="w-4 h-4 text-zinc-500" />
              <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Company Information</h2>
            </div>
            <div className="p-6 space-y-6">
              {/* Name */}
              <div>
                <label className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold mb-2">
                  Company Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-white/30 transition-colors"
                  placeholder="Enter company name"
                />
              </div>

              {/* Industry */}
              <div>
                <label className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold mb-2">
                  Industry
                </label>
                <select
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  className="w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none"
                >
                  <option value="">Select industry</option>
                  {INDUSTRIES.map((ind) => (
                    <option key={ind} value={ind}>{ind}</option>
                  ))}
                </select>
              </div>

              {/* Size */}
              <div>
                <label className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold mb-2">
                  Company Size
                </label>
                <select
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  className="w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none"
                >
                  <option value="">Select size</option>
                  {SIZES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>

              {/* Save Button */}
              <div className="flex items-center gap-4 pt-2">
                <button
                  onClick={handleSave}
                  disabled={saving || !hasChanges}
                  className="flex items-center gap-2 px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? (
                    <>
                      <span className="w-3 h-3 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                      Saving...
                    </>
                  ) : saveSuccess ? (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      Saved
                    </>
                  ) : (
                    'Save Changes'
                  )}
                </button>
                {hasChanges && !saving && (
                  <span className="text-[10px] text-amber-500 uppercase tracking-wider">Unsaved changes</span>
                )}
              </div>
            </div>
          </div>

          {/* Locations */}
          <div className="border border-white/10 bg-zinc-900/30">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <MapPin className="w-4 h-4 text-zinc-500" />
                <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Business Locations</h2>
              </div>
              <button
                onClick={() => navigate('/app/matcha/compliance')}
                className="text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors border border-white/10 px-3 py-1.5"
              >
                Manage in Compliance
              </button>
            </div>
            <div className="p-6">
              <p className="text-sm text-zinc-500">
                Business locations are managed through the Compliance page, where you can add shops, track jurisdiction requirements, and order compliance posters.
              </p>
            </div>
          </div>

          <div data-tour="company-setup-card" className="border border-white/10 bg-zinc-900/30">
            <div className="p-6 border-b border-white/10 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <Settings className="w-4 h-4 text-zinc-500" />
                <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Setup & Integrations</h2>
              </div>
              <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-wider ${googleBadge.tone}`}>
                {googleBadge.label}
              </span>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-zinc-500">
                Configure Google Workspace once here, then automatically provision employee accounts during onboarding.
              </p>

              {googleStatusError && (
                <p className="text-xs text-red-300">Status check failed: {googleStatusError}</p>
              )}

              <div data-tour="company-google-status" className="space-y-1 text-[11px] text-zinc-400">
                <p>Mode: <span className="text-zinc-200">{googleStatus?.mode || 'not configured'}</span></p>
                <p>Domain: <span className="text-zinc-200">{googleStatus?.domain || 'not set'}</span></p>
                <p>Auto-provision: <span className="text-zinc-200">{googleStatus?.auto_provision_on_employee_create ? 'on' : 'off'}</span></p>
              </div>

              <button
                data-tour="company-google-configure-btn"
                onClick={() => navigate('/app/matcha/google-workspace')}
                className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
              >
                Configure Google Workspace
              </button>
            </div>
          </div>
        </div>

        {/* Logo Sidebar */}
        <div className="space-y-8">
          <div data-tour="company-logo-card" className="border border-white/10 bg-zinc-900/30">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Company Logo</h2>
            </div>
            <div className="p-6 flex flex-col items-center">
              {/* Logo Preview */}
              <div className="w-40 h-40 border border-white/10 bg-zinc-950 flex items-center justify-center mb-6 overflow-hidden">
                {logoPreview ? (
                  <img
                    src={logoPreview}
                    alt="Company logo"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="flex flex-col items-center gap-2 text-zinc-600">
                    <Building className="w-10 h-10" />
                    <span className="text-[10px] uppercase tracking-wider">No logo</span>
                  </div>
                )}
              </div>

              {/* Upload Button */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleLogoUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={logoUploading}
                className="flex items-center gap-2 px-4 py-2 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all disabled:opacity-50"
              >
                {logoUploading ? (
                  <>
                    <span className="w-3 h-3 border-2 border-current/20 border-t-current rounded-full animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    Upload Logo
                  </>
                )}
              </button>
              <p className="text-[10px] text-zinc-600 mt-3 text-center">
                PNG, JPG or SVG. Max 5MB.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CompanyProfile;
