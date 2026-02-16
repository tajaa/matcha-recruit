import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChevronLeft, Upload, X, Plus } from 'lucide-react';
import { handbooks } from '../api/client';
import { complianceAPI } from '../api/compliance';
import type { CompanyHandbookProfile, HandbookMode, HandbookSourceType } from '../types';

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
];

interface CustomSectionDraft {
  title: string;
  content: string;
}

const DEFAULT_PROFILE: CompanyHandbookProfile = {
  legal_name: '',
  dba: null,
  ceo_or_president: '',
  headcount: null,
  remote_workers: false,
  minors: false,
  tipped_employees: false,
  union_employees: false,
  federal_contracts: false,
  group_health_insurance: false,
  background_checks: false,
  hourly_employees: true,
  salaried_employees: false,
  commissioned_employees: false,
  tip_pooling: false,
};

export function HandbookForm() {
  const { id } = useParams<{ id?: string }>();
  const isEditing = !!id;
  const navigate = useNavigate();

  const [title, setTitle] = useState('');
  const [mode, setMode] = useState<HandbookMode>('single_state');
  const [sourceType, setSourceType] = useState<HandbookSourceType>('template');
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [profile, setProfile] = useState<CompanyHandbookProfile>(DEFAULT_PROFILE);
  const [customSections, setCustomSections] = useState<CustomSectionDraft[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploadedFileUrl, setUploadedFileUrl] = useState<string | null>(null);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locationsStates, setLocationsStates] = useState<string[]>([]);

  useEffect(() => {
    const loadDefaults = async () => {
      try {
        const [defaultProfile, locations] = await Promise.all([
          handbooks.getProfile().catch(() => null),
          complianceAPI.getLocations().catch(() => []),
        ]);

        if (!isEditing && defaultProfile) {
          setProfile({
            ...defaultProfile,
            dba: defaultProfile.dba ?? null,
            headcount: defaultProfile.headcount ?? null,
          });
        }

        const states = Array.from(new Set((locations || []).map((loc) => (loc.state || '').toUpperCase()).filter(Boolean))).sort();
        setLocationsStates(states);
      } catch (err) {
        console.error('Failed to load handbook defaults:', err);
      }
    };
    loadDefaults();
  }, [isEditing]);

  useEffect(() => {
    if (!isEditing || !id) return;
    const loadHandbook = async () => {
      try {
        setLoading(true);
        const data = await handbooks.get(id);
        setTitle(data.title);
        setMode(data.mode);
        setSourceType(data.source_type);
        setSelectedStates(Array.from(new Set((data.scopes || []).map((scope) => (scope.state || '').toUpperCase()))));
        setProfile({
          ...data.profile,
          dba: data.profile.dba ?? null,
          headcount: data.profile.headcount ?? null,
        });
        setUploadedFileUrl(data.file_url);
        setUploadedFilename(data.file_name);
      } catch (err) {
        console.error('Failed to load handbook:', err);
      } finally {
        setLoading(false);
      }
    };
    loadHandbook();
  }, [id, isEditing]);

  const visibleStates = useMemo(() => {
    const set = new Set<string>([...locationsStates, ...US_STATES]);
    return Array.from(set).sort();
  }, [locationsStates]);

  const toggleState = (state: string) => {
    setSelectedStates((prev) => {
      const exists = prev.includes(state);
      if (mode === 'single_state') {
        return exists ? [] : [state];
      }
      return exists ? prev.filter((item) => item !== state) : [...prev, state];
    });
  };

  const setProfileField = (key: keyof CompanyHandbookProfile, value: string | number | boolean | null) => {
    setProfile((prev) => ({ ...prev, [key]: value }));
  };

  const handleSourceFileUpload = async () => {
    if (!file) return;
    try {
      const uploaded = await handbooks.uploadFile(file);
      setUploadedFileUrl(uploaded.url);
      setUploadedFilename(uploaded.filename);
      setFile(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to upload file';
      setError(msg);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError('Title is required');
      return;
    }
    if (selectedStates.length === 0) {
      setError('Select at least one state');
      return;
    }
    if (mode === 'single_state' && selectedStates.length !== 1) {
      setError('Single-state handbooks must have exactly one state');
      return;
    }
    if (mode === 'multi_state' && selectedStates.length < 2) {
      setError('Multi-state handbooks require at least two states');
      return;
    }
    if (sourceType === 'upload' && !uploadedFileUrl) {
      setError('Upload a handbook file before saving');
      return;
    }

    try {
      setLoading(true);
      const scopes = selectedStates.map((state) => ({
        state,
        city: null,
        zipcode: null,
        location_id: null,
      }));

      const normalizedProfile: CompanyHandbookProfile = {
        ...profile,
        legal_name: profile.legal_name?.trim() || '',
        ceo_or_president: profile.ceo_or_president?.trim() || '',
        dba: profile.dba?.trim() || null,
        headcount: typeof profile.headcount === 'number' ? profile.headcount : null,
      };

      if (!normalizedProfile.legal_name || !normalizedProfile.ceo_or_president) {
        setError('Legal name and CEO/President are required');
        return;
      }

      if (isEditing && id) {
        await handbooks.update(id, {
          title: title.trim(),
          mode,
          scopes,
          profile: normalizedProfile,
          file_url: uploadedFileUrl,
          file_name: uploadedFilename,
        });
        navigate(`/app/matcha/handbook/${id}`);
      } else {
        const created = await handbooks.create({
          title: title.trim(),
          mode,
          source_type: sourceType,
          scopes,
          profile: normalizedProfile,
          create_from_template: sourceType === 'template',
          file_url: uploadedFileUrl,
          file_name: uploadedFilename,
          custom_sections: customSections
            .filter((section) => section.title.trim())
            .map((section, index) => ({
              section_key: `custom_${index + 1}_${section.title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
              title: section.title.trim(),
              content: section.content.trim(),
              section_order: 300 + index,
              section_type: 'custom',
              jurisdiction_scope: {},
            })),
        });
        navigate(`/app/matcha/handbook/${created.id}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save handbook';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  if (loading && isEditing && !title) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading handbook...</div>
      </div>
    );
  }

  const boolFields: { key: keyof CompanyHandbookProfile; label: string }[] = [
    { key: 'remote_workers', label: 'Do you employ remote workers?' },
    { key: 'minors', label: 'Do you employ minors?' },
    { key: 'tipped_employees', label: 'Do you employ tipped employees?' },
    { key: 'union_employees', label: 'Do you have union employees?' },
    { key: 'federal_contracts', label: 'Do you have federal contracts?' },
    { key: 'group_health_insurance', label: 'Do you offer group health insurance?' },
    { key: 'background_checks', label: 'Do you conduct background checks?' },
    { key: 'hourly_employees', label: 'Do you employ hourly employees?' },
    { key: 'salaried_employees', label: 'Do you employ salaried employees?' },
    { key: 'commissioned_employees', label: 'Do you have commissioned employees?' },
    { key: 'tip_pooling', label: 'Do you use tip pooling?' },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-10">
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
            {isEditing ? 'Edit Handbook' : 'Create Handbook'}
          </h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            {isEditing ? 'Update handbook scope and employer settings' : 'Build handbook from template or upload'}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        <div className="space-y-4">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Handbook Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
            placeholder="e.g. 2026 Employee Handbook"
            required
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Handbook Type</label>
            <select
              value={mode}
              onChange={(e) => {
                const next = e.target.value as HandbookMode;
                setMode(next);
                if (next === 'single_state' && selectedStates.length > 1) {
                  setSelectedStates(selectedStates.slice(0, 1));
                }
              }}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
            >
              <option value="single_state">Single-State</option>
              <option value="multi_state">Multi-State</option>
            </select>
          </div>
          {!isEditing && (
            <div className="space-y-2">
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Source</label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as HandbookSourceType)}
                className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
              >
                <option value="template">Template Builder</option>
                <option value="upload">Upload Existing Handbook</option>
              </select>
            </div>
          )}
        </div>

        <div className="space-y-3">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">
            {mode === 'single_state' ? 'Select State' : 'Select States'}
          </label>
          <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
            {visibleStates.map((state) => {
              const selected = selectedStates.includes(state);
              return (
                <button
                  key={state}
                  type="button"
                  onClick={() => toggleState(state)}
                  className={`px-2 py-1 text-[10px] font-mono border transition-colors ${
                    selected
                      ? 'bg-white text-black border-white'
                      : 'bg-zinc-900 text-zinc-400 border-white/20 hover:border-white/40'
                  }`}
                >
                  {state}
                </button>
              );
            })}
          </div>
          <p className="text-[10px] text-zinc-500 font-mono">
            Compliance locations found: {locationsStates.length > 0 ? locationsStates.join(', ') : 'none'}.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Company Legal Name</label>
            <input
              type="text"
              value={profile.legal_name}
              onChange={(e) => setProfileField('legal_name', e.target.value)}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">DBA (optional)</label>
            <input
              type="text"
              value={profile.dba || ''}
              onChange={(e) => setProfileField('dba', e.target.value || null)}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">CEO or President</label>
            <input
              type="text"
              value={profile.ceo_or_president}
              onChange={(e) => setProfileField('ceo_or_president', e.target.value)}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Headcount</label>
            <input
              type="number"
              value={profile.headcount ?? ''}
              onChange={(e) => setProfileField('headcount', e.target.value ? Number(e.target.value) : null)}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
              min={0}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 bg-zinc-900/40 p-4">
          {boolFields.map((field) => (
            <label key={field.key} className="flex items-center justify-between text-xs text-zinc-300">
              <span>{field.label}</span>
              <input
                type="checkbox"
                checked={Boolean(profile[field.key])}
                onChange={(e) => setProfileField(field.key, e.target.checked)}
                className="h-4 w-4 accent-white"
              />
            </label>
          ))}
        </div>

        {sourceType === 'upload' && !isEditing && (
          <div className="space-y-3 border border-white/10 bg-zinc-900/40 p-4">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Upload Handbook Document</label>
            <div className="flex items-center gap-3">
              <label className="px-3 py-2 border border-white/20 text-xs uppercase tracking-wider text-zinc-300 hover:text-white cursor-pointer">
                Select File
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              {file && <span className="text-xs text-zinc-400 truncate">{file.name}</span>}
              {file && (
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  className="text-zinc-500 hover:text-red-400"
                >
                  <X size={14} />
                </button>
              )}
              <button
                type="button"
                onClick={handleSourceFileUpload}
                disabled={!file}
                className="ml-auto px-3 py-2 bg-white text-black text-xs uppercase tracking-wider disabled:opacity-50 flex items-center gap-1"
              >
                <Upload size={12} />
                Upload
              </button>
            </div>
            {uploadedFileUrl && (
              <div className="text-[11px] text-emerald-400 font-mono">
                Uploaded: {uploadedFilename || 'handbook'}
              </div>
            )}
          </div>
        )}

        {sourceType === 'template' && !isEditing && (
          <div className="space-y-3 border border-white/10 bg-zinc-900/40 p-4">
            <div className="flex items-center justify-between">
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Custom Company Sections</label>
              <button
                type="button"
                onClick={() => setCustomSections((prev) => [...prev, { title: '', content: '' }])}
                className="text-xs text-zinc-300 hover:text-white uppercase tracking-wider flex items-center gap-1"
              >
                <Plus size={12} />
                Add Section
              </button>
            </div>
            {customSections.length === 0 ? (
              <p className="text-xs text-zinc-500">No custom sections added.</p>
            ) : (
              <div className="space-y-3">
                {customSections.map((section, index) => (
                  <div key={index} className="border border-white/10 p-3 space-y-2">
                    <input
                      type="text"
                      value={section.title}
                      onChange={(e) =>
                        setCustomSections((prev) => prev.map((item, i) => (i === index ? { ...item, title: e.target.value } : item)))
                      }
                      placeholder="Section title"
                      className="w-full px-3 py-2 bg-zinc-950 border border-white/20 text-white text-sm"
                    />
                    <textarea
                      value={section.content}
                      onChange={(e) =>
                        setCustomSections((prev) => prev.map((item, i) => (i === index ? { ...item, content: e.target.value } : item)))
                      }
                      placeholder="Section content"
                      className="w-full px-3 py-2 bg-zinc-950 border border-white/20 text-white text-sm min-h-[90px] resize-y"
                    />
                    <button
                      type="button"
                      onClick={() => setCustomSections((prev) => prev.filter((_, i) => i !== index))}
                      className="text-[10px] text-red-400 hover:text-red-300 uppercase tracking-wider"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="text-red-400 text-xs font-medium px-4 py-3 border border-red-500/30 bg-red-500/10 rounded-sm">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-4 pt-6 border-t border-white/10">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-6 py-2 text-zinc-500 hover:text-white text-xs font-medium uppercase tracking-wider transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-8 py-2 bg-white hover:bg-zinc-200 text-black rounded-sm text-xs font-medium uppercase tracking-wider transition-colors disabled:opacity-50"
          >
            {loading ? 'Saving...' : isEditing ? 'Update Handbook' : 'Create Handbook'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default HandbookForm;

