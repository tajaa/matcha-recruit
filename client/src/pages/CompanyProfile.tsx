import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building, Upload, Check, AlertTriangle, MapPin, Settings, Briefcase, Heart } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getAccessToken, provisioning } from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type { ClientProfile, GoogleWorkspaceConnectionStatus } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const INDUSTRIES = [
  'Technology', 'Healthcare', 'Finance', 'Education', 'Retail',
  'Manufacturing', 'Construction', 'Hospitality', 'Transportation',
  'Real Estate', 'Legal', 'Media', 'Nonprofit', 'Government', 'Other',
];

const HEALTHCARE_SPECIALTIES = [
  { value: 'oncology', label: 'Oncology' },
];

const SIZES = [
  { value: 'startup', label: '1-50 employees' },
  { value: 'mid', label: '51-500 employees' },
  { value: 'enterprise', label: '500+ employees' },
];

const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
  'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
  'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
  'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
  'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
  'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
  'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
  'Wisconsin', 'Wyoming',
];

const WORK_ARRANGEMENTS = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'in_office', label: 'In-Office' },
];

const EMPLOYMENT_TYPES = [
  { value: 'at_will', label: 'At-Will' },
  { value: 'contract', label: 'Contract' },
  { value: 'other', label: 'Other' },
];

interface CompanyData {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  logo_url: string | null;
  headquarters_state: string | null;
  headquarters_city: string | null;
  work_arrangement: string | null;
  default_employment_type: string | null;
  benefits_summary: string | null;
  pto_policy_summary: string | null;
  compensation_notes: string | null;
  company_values: string | null;
  ai_guidance_notes: string | null;
  healthcare_specialties: string[] | null;
}

const LT = {
  section: 'bg-stone-100 rounded-2xl',
  cardLight: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  sectionHeader: 'p-6 border-b border-stone-200 flex items-center gap-3',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  input: 'w-full bg-white border border-stone-300 px-4 py-3 text-sm text-zinc-900 placeholder-stone-400 rounded-xl focus:outline-none focus:border-stone-400 transition-colors',
  select: 'w-full bg-white border border-stone-300 px-4 py-3 text-sm text-zinc-900 rounded-xl focus:outline-none focus:border-stone-400 transition-colors appearance-none',
  textarea: 'w-full bg-stone-50 border border-stone-300 px-4 py-3 text-sm text-zinc-900 placeholder-stone-400 rounded-xl focus:outline-none focus:border-stone-400 transition-colors resize-none',
  label: 'block text-[10px] uppercase tracking-[0.2em] text-stone-500 font-bold mb-2',
  helper: 'text-[10px] text-stone-400 mt-1.5',
  sectionTitle: 'text-xs font-bold text-zinc-900 uppercase tracking-[0.2em]',
  sectionIcon: 'w-4 h-4 text-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-600 hover:text-zinc-900',
  btnGhost: 'text-stone-400 hover:text-zinc-900',
  alertError: 'bg-red-50 border border-red-200 rounded-xl',
  alertErrorText: 'text-red-700',
  logoBg: 'border border-stone-200 bg-stone-200',
  logoPlaceholder: 'text-stone-400',
  logoHelper: 'text-stone-400',
  logoUploadBtn: 'border border-stone-300 hover:bg-zinc-900 hover:text-white text-stone-600',
  tipCard: 'border border-stone-200 bg-stone-100 rounded-2xl',
  tipText: 'text-stone-500',
  tipStrong: 'text-zinc-900',
  profileBadge: 'border border-emerald-300 bg-emerald-50 text-emerald-700',
  badgeChecking: 'border-stone-300 bg-stone-200 text-stone-600',
  badgeDisconnected: 'border-stone-300 bg-stone-200 text-stone-600',
  badgeConnected: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  badgeError: 'border-red-300 bg-red-50 text-red-700',
  badgeDefault: 'border-amber-300 bg-amber-50 text-amber-700',
  googleDetail: 'text-stone-500',
  googleValue: 'text-zinc-900',
} as const;

const DK = {
  section: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardLight: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  sectionHeader: 'p-6 border-b border-white/10 flex items-center gap-3',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  input: 'w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white placeholder-zinc-600 rounded-xl focus:outline-none focus:border-white/30 transition-colors',
  select: 'w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white rounded-xl focus:outline-none focus:border-white/30 transition-colors appearance-none',
  textarea: 'w-full bg-zinc-950 border border-white/10 px-4 py-3 text-sm text-white placeholder-zinc-600 rounded-xl focus:outline-none focus:border-white/30 transition-colors resize-none',
  label: 'block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold mb-2',
  helper: 'text-[10px] text-zinc-600 mt-1.5',
  sectionTitle: 'text-xs font-bold text-white uppercase tracking-[0.2em]',
  sectionIcon: 'w-4 h-4 text-zinc-500',
  btnPrimary: 'bg-white text-black hover:bg-zinc-200',
  btnSecondary: 'border border-white/10 text-zinc-400 hover:text-white',
  btnGhost: 'text-zinc-500 hover:text-white',
  alertError: 'bg-red-500/10 border border-red-500/20 rounded-xl',
  alertErrorText: 'text-red-400',
  logoBg: 'border border-white/10 bg-zinc-950',
  logoPlaceholder: 'text-zinc-600',
  logoHelper: 'text-zinc-600',
  logoUploadBtn: 'border border-white/20 hover:bg-white hover:text-black text-zinc-400',
  tipCard: 'border border-white/10 bg-zinc-900/30 rounded-2xl',
  tipText: 'text-zinc-400',
  tipStrong: 'text-zinc-300',
  profileBadge: 'border border-emerald-500/20 bg-emerald-900/10 text-emerald-400',
  badgeChecking: 'border-zinc-700 bg-zinc-900/70 text-zinc-300',
  badgeDisconnected: 'border-zinc-700 bg-zinc-900/70 text-zinc-300',
  badgeConnected: 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200',
  badgeError: 'border-red-500/40 bg-red-950/30 text-red-200',
  badgeDefault: 'border-amber-500/40 bg-amber-950/30 text-amber-200',
  googleDetail: 'text-zinc-400',
  googleValue: 'text-zinc-200',
} as const;

export function CompanyProfile() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const clientProfile = profile as ClientProfile | null;
  const companyId = clientProfile?.company_id;
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [company, setCompany] = useState<CompanyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState<string | null>(null);

  // Form fields — existing
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('');
  const [size, setSize] = useState('');

  // Form fields — new profile fields
  const [headquartersState, setHeadquartersState] = useState('');
  const [headquartersCity, setHeadquartersCity] = useState('');
  const [workArrangement, setWorkArrangement] = useState('');
  const [defaultEmploymentType, setDefaultEmploymentType] = useState('');
  const [benefitsSummary, setBenefitsSummary] = useState('');
  const [ptoPolicySummary, setPtoPolicySummary] = useState('');
  const [compensationNotes, setCompensationNotes] = useState('');
  const [companyValues, setCompanyValues] = useState('');
  const [aiGuidanceNotes, setAiGuidanceNotes] = useState('');
  const [healthcareSpecialties, setHealthcareSpecialties] = useState<string[]>([]);

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
      setHealthcareSpecialties(data.healthcare_specialties || []);
      setHeadquartersState(data.headquarters_state || '');
      setHeadquartersCity(data.headquarters_city || '');
      setWorkArrangement(data.work_arrangement || '');
      setDefaultEmploymentType(data.default_employment_type || '');
      setBenefitsSummary(data.benefits_summary || '');
      setPtoPolicySummary(data.pto_policy_summary || '');
      setCompensationNotes(data.compensation_notes || '');
      setCompanyValues(data.company_values || '');
      setAiGuidanceNotes(data.ai_guidance_notes || '');
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
      const body: Record<string, string | string[]> = {};
      if (name !== (company?.name || '')) body.name = name;
      if (industry !== (company?.industry || '')) body.industry = industry;
      if (size !== (company?.size || '')) body.size = size;
      if (headquartersState !== (company?.headquarters_state || '')) body.headquarters_state = headquartersState;
      if (headquartersCity !== (company?.headquarters_city || '')) body.headquarters_city = headquartersCity;
      if (workArrangement !== (company?.work_arrangement || '')) body.work_arrangement = workArrangement;
      if (defaultEmploymentType !== (company?.default_employment_type || '')) body.default_employment_type = defaultEmploymentType;
      if (benefitsSummary !== (company?.benefits_summary || '')) body.benefits_summary = benefitsSummary;
      if (ptoPolicySummary !== (company?.pto_policy_summary || '')) body.pto_policy_summary = ptoPolicySummary;
      if (compensationNotes !== (company?.compensation_notes || '')) body.compensation_notes = compensationNotes;
      if (companyValues !== (company?.company_values || '')) body.company_values = companyValues;
      if (aiGuidanceNotes !== (company?.ai_guidance_notes || '')) body.ai_guidance_notes = aiGuidanceNotes;
      // Healthcare specialties — clear when industry changes away from Healthcare
      const effectiveSpecialties = industry === 'Healthcare' ? healthcareSpecialties : [];
      const prevSpecialties = company?.healthcare_specialties || [];
      if (JSON.stringify(effectiveSpecialties) !== JSON.stringify(prevSpecialties)) {
        body.healthcare_specialties = effectiveSpecialties;
      }

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
      setLogoPreview(company?.logo_url || null);
    } finally {
      setLogoUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const hasChanges =
    name !== (company?.name || '') ||
    industry !== (company?.industry || '') ||
    size !== (company?.size || '') ||
    headquartersState !== (company?.headquarters_state || '') ||
    headquartersCity !== (company?.headquarters_city || '') ||
    workArrangement !== (company?.work_arrangement || '') ||
    defaultEmploymentType !== (company?.default_employment_type || '') ||
    benefitsSummary !== (company?.benefits_summary || '') ||
    ptoPolicySummary !== (company?.pto_policy_summary || '') ||
    compensationNotes !== (company?.compensation_notes || '') ||
    companyValues !== (company?.company_values || '') ||
    aiGuidanceNotes !== (company?.ai_guidance_notes || '') ||
    JSON.stringify(industry === 'Healthcare' ? healthcareSpecialties : []) !== JSON.stringify(company?.healthcare_specialties || []);

  const googleBadge = (() => {
    if (loadingGoogle) return { label: 'Checking', tone: t.badgeChecking };
    if (!googleStatus || googleStatus.status === 'disconnected') return { label: 'Not Connected', tone: t.badgeDisconnected };
    if (googleStatus.status === 'connected') return { label: 'Connected', tone: t.badgeConnected };
    if (googleStatus.status === 'error') return { label: 'Needs Attention', tone: t.badgeError };
    return { label: googleStatus.status.toUpperCase(), tone: t.badgeDefault };
  })();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          <span className={`text-xs ${t.textMuted} font-mono uppercase tracking-wider`}>Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header */}
      <div className={`flex flex-col sm:flex-row sm:items-end justify-between gap-6 border-b ${t.border} pb-8`}>
        <div className="text-center sm:text-left">
          <div className="flex items-center gap-3 mb-2 justify-center sm:justify-start">
            <div className={`px-2 py-1 ${t.profileBadge} text-[9px] uppercase tracking-widest font-mono rounded-lg`}>
              Company Profile
            </div>
          </div>
          <h1 className={`text-4xl md:text-5xl font-bold tracking-tighter ${t.textMain} uppercase break-all`}>
            {company?.name || 'Company'}
          </h1>
        </div>
        <div className="flex items-center gap-3 justify-center sm:justify-end">
          {hasChanges && (
            <button
              onClick={handleSave}
              disabled={saving}
              className={`flex items-center gap-2 px-5 py-2.5 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {saving ? (
                <>
                  <span className="w-3 h-3 border-2 border-current/20 border-t-current rounded-full animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </button>
          )}
          {saveSuccess && (
            <span className="flex items-center gap-1.5 text-emerald-400 text-xs uppercase tracking-wider">
              <Check className="w-3.5 h-3.5" /> Saved
            </span>
          )}
          <div data-tour="company-setup-guide">
            <FeatureGuideTrigger guideId="company-setup" />
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className={`flex items-center gap-3 p-4 ${t.alertError}`}>
          <AlertTriangle className={`w-4 h-4 ${t.alertErrorText} shrink-0`} />
          <p className={`text-sm ${t.alertErrorText}`}>{error}</p>
          <button onClick={() => setError(null)} className={`ml-auto ${t.alertErrorText} text-xs uppercase tracking-wider`}>
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-8">
          {/* Section 1: Company Information */}
          <div data-tour="company-info-form" className={t.section}>
            <div className={t.sectionHeader}>
              <Building className={t.sectionIcon} />
              <h2 className={t.sectionTitle}>Company Information</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className={t.label}>Company Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} className={t.input} placeholder="Enter company name" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <label className={t.label}>Industry</label>
                  <select value={industry} onChange={(e) => setIndustry(e.target.value)} className={t.select}>
                    <option value="">Select industry</option>
                    {INDUSTRIES.map((ind) => (<option key={ind} value={ind}>{ind}</option>))}
                  </select>
                  {industry === 'Healthcare' && (
                    <div className="mt-3">
                      <label className={`${t.label} mb-2`}>Healthcare Specialties</label>
                      <div className="flex flex-wrap gap-3">
                        {HEALTHCARE_SPECIALTIES.map((spec) => (
                          <label key={spec.value} className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={healthcareSpecialties.includes(spec.value)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setHealthcareSpecialties([...healthcareSpecialties, spec.value]);
                                } else {
                                  setHealthcareSpecialties(healthcareSpecialties.filter((s) => s !== spec.value));
                                }
                              }}
                              className="rounded border-zinc-600"
                            />
                            <span className={`text-sm ${isLight ? 'text-zinc-700' : 'text-zinc-300'}`}>{spec.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div>
                  <label className={t.label}>Company Size</label>
                  <select value={size} onChange={(e) => setSize(e.target.value)} className={t.select}>
                    <option value="">Select size</option>
                    {SIZES.map((s) => (<option key={s.value} value={s.value}>{s.label}</option>))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <label className={t.label}>Headquarters State</label>
                  <select value={headquartersState} onChange={(e) => setHeadquartersState(e.target.value)} className={t.select}>
                    <option value="">Select state</option>
                    {US_STATES.map((s) => (<option key={s} value={s}>{s}</option>))}
                  </select>
                  <p className={t.helper}>Used for jurisdiction-aware legal guidance</p>
                </div>
                <div>
                  <label className={t.label}>Headquarters City</label>
                  <input type="text" value={headquartersCity} onChange={(e) => setHeadquartersCity(e.target.value)} className={t.input} placeholder="e.g. San Francisco" />
                  <p className={t.helper}>City-level wage and tax guidance</p>
                </div>
              </div>
              <div>
                <label className={t.label}>Work Arrangement</label>
                <select value={workArrangement} onChange={(e) => setWorkArrangement(e.target.value)} className={t.select}>
                  <option value="">Select arrangement</option>
                  {WORK_ARRANGEMENTS.map((w) => (<option key={w.value} value={w.value}>{w.label}</option>))}
                </select>
                <p className={t.helper}>Affects offer letter and onboarding language</p>
              </div>
            </div>
          </div>

          {/* Section 2: Employment & Compensation */}
          <div className={t.section}>
            <div className={t.sectionHeader}>
              <Briefcase className={t.sectionIcon} />
              <h2 className={t.sectionTitle}>Employment & Compensation</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className={t.label}>Default Employment Type</label>
                <select value={defaultEmploymentType} onChange={(e) => setDefaultEmploymentType(e.target.value)} className={t.select}>
                  <option value="">Select type</option>
                  {EMPLOYMENT_TYPES.map((et) => (<option key={et.value} value={et.value}>{et.label}</option>))}
                </select>
                <p className={t.helper}>Pre-fills offer letters with this employment type</p>
              </div>
              <div>
                <label className={t.label}>Compensation Notes</label>
                <textarea value={compensationNotes} onChange={(e) => setCompensationNotes(e.target.value)} className={t.textarea} rows={3} placeholder="e.g. Paid bi-weekly. Equity vesting over 4 years with 1-year cliff. Annual bonus target 10-15%." />
                <p className={t.helper}>Pay frequency, equity, and bonus structure for offer letter guidance</p>
              </div>
              <div>
                <label className={t.label}>Benefits Summary</label>
                <textarea value={benefitsSummary} onChange={(e) => setBenefitsSummary(e.target.value)} className={t.textarea} rows={4} placeholder="e.g. Medical, dental, vision (100% employee, 75% dependents). 401(k) with 4% match. $500/yr learning stipend." />
                <p className={t.helper}>Standard benefits package — pre-fills offer letters automatically</p>
              </div>
              <div>
                <label className={t.label}>PTO Policy Summary</label>
                <textarea value={ptoPolicySummary} onChange={(e) => setPtoPolicySummary(e.target.value)} className={t.textarea} rows={3} placeholder="e.g. Unlimited PTO with 2-week minimum. 10 company holidays. 12 weeks parental leave." />
                <p className={t.helper}>PTO overview for offer letters and onboarding documents</p>
              </div>
            </div>
          </div>

          {/* Section 3: Culture & AI Guidance */}
          <div className={t.section}>
            <div className={t.sectionHeader}>
              <Heart className={t.sectionIcon} />
              <h2 className={t.sectionTitle}>Culture & AI Guidance</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className={t.label}>Company Values</label>
                <textarea value={companyValues} onChange={(e) => setCompanyValues(e.target.value)} className={t.textarea} rows={4} placeholder="e.g. Move fast, own outcomes. Default to transparency. Customers come first. Disagree and commit." />
                <p className={t.helper}>Sets the tone for reviews, workbooks, and onboarding content</p>
              </div>
              <div>
                <label className={t.label}>AI Guidance Notes</label>
                <textarea value={aiGuidanceNotes} onChange={(e) => setAiGuidanceNotes(e.target.value)} className={t.textarea} rows={4} placeholder='e.g. Always mention our 90-day review period in offer letters. Use "team member" instead of "employee". Include our diversity commitment in all onboarding documents.' />
                <p className={t.helper}>
                  Special instructions for the AI — anything written here will be included in every AI-generated document
                </p>
              </div>
            </div>
          </div>

          {/* Locations */}
          <div className={t.section}>
            <div className="p-6 border-b flex items-center justify-between" style={{}}>
              <div className={`flex items-center gap-3 border-0 ${t.border}`}>
                <MapPin className={t.sectionIcon} />
                <h2 className={t.sectionTitle}>Business Locations</h2>
              </div>
              <button
                onClick={() => navigate('/app/matcha/compliance')}
                className={`text-[10px] uppercase tracking-[0.2em] ${t.btnSecondary} px-3 py-1.5 rounded-lg transition-colors`}
              >
                Manage in Compliance
              </button>
            </div>
            <div className="p-6">
              <p className={`text-sm ${t.textMuted}`}>
                Business locations are managed through the Compliance page, where you can add shops, track jurisdiction requirements, and order compliance posters.
              </p>
            </div>
          </div>

          <div data-tour="company-setup-card" className={t.section}>
            <div className={`p-6 border-b ${t.border} flex items-center justify-between gap-3`}>
              <div className="flex items-center gap-3">
                <Settings className={t.sectionIcon} />
                <h2 className={t.sectionTitle}>Setup & Integrations</h2>
              </div>
              <span className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-wider ${googleBadge.tone}`}>
                {googleBadge.label}
              </span>
            </div>
            <div className="p-6 space-y-4">
              <p className={`text-sm ${t.textMuted}`}>
                Configure Google Workspace once here, then automatically provision employee accounts during onboarding.
              </p>

              {googleStatusError && (
                <p className="text-xs text-red-300">Status check failed: {googleStatusError}</p>
              )}

              <div data-tour="company-google-status" className={`space-y-1 text-[11px] ${t.googleDetail}`}>
                <p>Mode: <span className={t.googleValue}>{googleStatus?.mode || 'not configured'}</span></p>
                <p>Domain: <span className={t.googleValue}>{googleStatus?.domain || 'not set'}</span></p>
                <p>Auto-provision: <span className={t.googleValue}>{googleStatus?.auto_provision_on_employee_create ? 'on' : 'off'}</span></p>
              </div>

              <button
                data-tour="company-google-configure-btn"
                onClick={() => navigate('/app/matcha/google-workspace')}
                className={`px-4 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
              >
                Configure Google Workspace
              </button>
            </div>
          </div>

          {/* Bottom save bar */}
          {hasChanges && (
            <div className="flex items-center gap-4">
              <button
                onClick={handleSave}
                disabled={saving}
                className={`flex items-center gap-2 px-6 py-3 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                {saving ? (
                  <>
                    <span className="w-3 h-3 border-2 border-current/20 border-t-current rounded-full animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save Changes'
                )}
              </button>
              <span className="text-[10px] text-amber-500 uppercase tracking-wider">Unsaved changes</span>
            </div>
          )}
        </div>

        {/* Logo Sidebar */}
        <div className="space-y-8">
          <div data-tour="company-logo-card" className={t.section}>
            <div className={`p-6 border-b ${t.border}`}>
              <h2 className={t.sectionTitle}>Company Logo</h2>
            </div>
            <div className="p-6 flex flex-col items-center">
              <div className={`w-40 h-40 ${t.logoBg} flex items-center justify-center mb-6 overflow-hidden rounded-xl`}>
                {logoPreview ? (
                  <img src={logoPreview} alt="Company logo" className="w-full h-full object-contain" />
                ) : (
                  <div className={`flex flex-col items-center gap-2 ${t.logoPlaceholder}`}>
                    <Building className="w-10 h-10" />
                    <span className="text-[10px] uppercase tracking-wider">No logo</span>
                  </div>
                )}
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={logoUploading}
                className={`flex items-center gap-2 px-4 py-2 ${t.logoUploadBtn} text-xs font-mono uppercase tracking-widest rounded-xl transition-all disabled:opacity-50`}
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
              <p className={`text-[10px] ${t.logoHelper} mt-3 text-center`}>
                PNG, JPG or SVG. Max 5MB.
              </p>
            </div>
          </div>

          {/* Profile completion sidebar hint */}
          <div className={`${t.tipCard} p-6`}>
            <h3 className={`${t.sectionTitle} mb-3`}>AI Profile Tips</h3>
            <ul className={`space-y-2.5 text-[11px] ${t.tipText}`}>
              <li className="flex gap-2">
                <span className="text-emerald-500 mt-0.5">&#x2022;</span>
                <span>Add your <strong className={t.tipStrong}>headquarters state</strong> so offer letters use the right legal defaults</span>
              </li>
              <li className="flex gap-2">
                <span className="text-emerald-500 mt-0.5">&#x2022;</span>
                <span>Fill in <strong className={t.tipStrong}>benefits</strong> and <strong className={t.tipStrong}>PTO</strong> to skip repetitive questions in chat</span>
              </li>
              <li className="flex gap-2">
                <span className="text-emerald-500 mt-0.5">&#x2022;</span>
                <span>Use <strong className={t.tipStrong}>AI guidance notes</strong> for custom rules like probation periods or preferred terminology</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CompanyProfile;
