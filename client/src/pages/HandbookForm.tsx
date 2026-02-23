import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Upload, X, Plus, CheckCircle2, Sparkles } from 'lucide-react';
import { handbooks } from '../api/client';
import { complianceAPI } from '../api/compliance';
import type { BusinessLocation } from '../api/compliance';
import type {
  CompanyHandbookProfile,
  HandbookGuidedQuestion,
  HandbookMode,
  HandbookScope,
  HandbookSourceType,
} from '../types';
import { FeatureGuideTrigger } from '../features/feature-guides';

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
];

const CREATE_STEPS = [
  'Business Profile',
  'State Scope',
  'Company Profile',
  'Policy Setup',
  'Review',
] as const;

const INDUSTRY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'general', label: 'General Employer' },
  { value: 'technology', label: 'Technology / Professional Services' },
  { value: 'hospitality', label: 'Hospitality / Restaurants' },
  { value: 'retail', label: 'Retail' },
  { value: 'manufacturing', label: 'Manufacturing / Warehouse' },
  { value: 'healthcare', label: 'Healthcare' },
];

const INDUSTRY_PLAYBOOK_PREVIEW: Record<string, { focus: string; boilerplate: string[] }> = {
  general: {
    focus: 'Baseline handbook for common employer operations with reporting and leave controls.',
    boilerplate: ['Core Employment Terms', 'Attendance and Leave Controls', 'Reporting and Anti-Retaliation'],
  },
  technology: {
    focus: 'Adds remote-work governance, privacy controls, and rapid incident escalation language.',
    boilerplate: ['Remote Work Compliance', 'Security and Privacy Rules', 'Investigation and Reporting'],
  },
  hospitality: {
    focus: 'Adds tipped-employee, tip-pool, and shift scheduling controls.',
    boilerplate: ['Tip Credit and Pooling Rules', 'Meal and Break Controls', 'Guest Incident Escalation'],
  },
  retail: {
    focus: 'Adds opening/closing controls, floor conduct standards, and loss-prevention workflows.',
    boilerplate: ['Shift and Timekeeping Controls', 'Customer Conduct Rules', 'Safety and Theft Escalation'],
  },
  manufacturing: {
    focus: 'Adds safety-critical controls, stop-work authority, and handoff requirements.',
    boilerplate: ['Safety and Stop-Work Authority', 'Shift Handoff Rules', 'Incident Reporting Controls'],
  },
  healthcare: {
    focus: 'Adds credentialing, patient-safety reporting, and accommodation controls.',
    boilerplate: ['Credentialing Controls', 'Patient Safety Reporting', 'Accommodation and Non-Retaliation'],
  },
};

const QUICK_SIGNAL_FIELDS: Array<{ key: keyof CompanyHandbookProfile; label: string }> = [
  { key: 'remote_workers', label: 'Remote Workforce' },
  { key: 'tipped_employees', label: 'Tipped Staff' },
  { key: 'union_employees', label: 'Union Environment' },
  { key: 'federal_contracts', label: 'Federal Contracts' },
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
  const isWizard = !isEditing;
  const navigate = useNavigate();

  const [title, setTitle] = useState('');
  const [mode, setMode] = useState<HandbookMode>('single_state');
  const [sourceType, setSourceType] = useState<HandbookSourceType>('template');
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [profile, setProfile] = useState<CompanyHandbookProfile>(DEFAULT_PROFILE);
  const [existingScopes, setExistingScopes] = useState<HandbookScope[]>([]);
  const [customSections, setCustomSections] = useState<CustomSectionDraft[]>([]);
  const [industry, setIndustry] = useState('general');
  const [subIndustry, setSubIndustry] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploadedFileUrl, setUploadedFileUrl] = useState<string | null>(null);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guidedQuestions, setGuidedQuestions] = useState<HandbookGuidedQuestion[]>([]);
  const [guidedAnswers, setGuidedAnswers] = useState<Record<string, string>>({});
  const [guidedSummary, setGuidedSummary] = useState<string | null>(null);
  const [guidedLoading, setGuidedLoading] = useState(false);
  const [guidedError, setGuidedError] = useState<string | null>(null);
  const [companyLocations, setCompanyLocations] = useState<BusinessLocation[]>([]);
  const [locationsStates, setLocationsStates] = useState<string[]>([]);
  const [currentStep, setCurrentStep] = useState(0);

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
        setCompanyLocations(locations || []);
        setLocationsStates(states);
      } catch {
        // Non-blocking defaults fetch; keep wizard usable with static state list.
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
        setExistingScopes(data.scopes || []);
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

  const selectedIndustryLabel =
    INDUSTRY_OPTIONS.find((option) => option.value === industry)?.label || industry;
  const industryPlaybook =
    INDUSTRY_PLAYBOOK_PREVIEW[industry] || INDUSTRY_PLAYBOOK_PREVIEW.general;
  const unansweredGuidedCount = guidedQuestions.filter(
    (question) => !(guidedAnswers[question.id] || '').trim()
  ).length;
  const answeredGuidedCount = guidedQuestions.length - unansweredGuidedCount;

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

  const mergeSuggestedSections = (incoming: Array<{ title: string; content: string }>) => {
    if (!incoming.length) return;
    setCustomSections((prev) => {
      const seen = new Set(
        prev.map((section) => section.title.trim().toLowerCase()).filter(Boolean)
      );
      const additions: CustomSectionDraft[] = [];
      for (const section of incoming) {
        const title = section.title?.trim();
        const content = section.content?.trim();
        const key = title?.toLowerCase() || '';
        if (!title || !content || seen.has(key)) continue;
        seen.add(key);
        additions.push({ title, content });
      }
      return additions.length ? [...prev, ...additions] : prev;
    });
  };

  const buildGuidedAnswersPayload = () => {
    const enrichedAnswers = { ...guidedAnswers };
    const businessSignals = QUICK_SIGNAL_FIELDS
      .filter((field) => Boolean(profile[field.key]))
      .map((field) => field.label);

    const defaults: Record<string, string> = {
      industry_profile: selectedIndustryLabel,
      business_sub_industry: subIndustry.trim(),
      business_model_signals: businessSignals.join(', '),
      target_states: selectedStates.join(', '),
      handbook_source: sourceType === 'template' ? 'Template Builder' : 'Uploaded Handbook',
    };

    for (const [key, value] of Object.entries(defaults)) {
      const normalized = value.trim();
      if (!normalized) continue;
      if ((enrichedAnswers[key] || '').trim()) continue;
      enrichedAnswers[key] = normalized;
    }

    return enrichedAnswers;
  };

  const buildScopesFromSelectedStates = (states: string[]): Omit<HandbookScope, 'id'>[] => {
    const normalizedStates = states.map((state) => state.toUpperCase());
    const selectedStateSet = new Set(normalizedStates);
    const locationScopes = (companyLocations || [])
      .filter((loc) => selectedStateSet.has((loc.state || '').toUpperCase()))
      .map((loc) => ({
        state: (loc.state || '').toUpperCase(),
        city: loc.city || null,
        zipcode: loc.zipcode || null,
        location_id: loc.id || null,
      }));

    const dedupedLocationScopes: Omit<HandbookScope, 'id'>[] = [];
    const seen = new Set<string>();
    for (const scope of locationScopes) {
      const key = `${scope.state}|${scope.city || ''}|${scope.zipcode || ''}|${scope.location_id || ''}`;
      if (seen.has(key)) continue;
      seen.add(key);
      dedupedLocationScopes.push(scope);
    }

    const statesCoveredByLocations = new Set(dedupedLocationScopes.map((scope) => scope.state));
    const fallbackStateScopes = normalizedStates
      .filter((state) => !statesCoveredByLocations.has(state))
      .map((state) => ({
        state,
        city: null,
        zipcode: null,
        location_id: null,
      }));

    return [...dedupedLocationScopes, ...fallbackStateScopes];
  };

  const handleGenerateGuidedDraft = async () => {
    setGuidedError(null);
    setError(null);

    const companyError = getStepError(2);
    const scopeError = getStepError(1);
    if (companyError || scopeError) {
      setGuidedError(companyError || scopeError || 'Complete required setup fields first.');
      return;
    }

    const normalizedSelectedStates = selectedStates.map((state) => state.toUpperCase());
    const scopes = buildScopesFromSelectedStates(normalizedSelectedStates);

    const normalizedProfile: CompanyHandbookProfile = {
      ...profile,
      legal_name: profile.legal_name?.trim() || '',
      ceo_or_president: profile.ceo_or_president?.trim() || '',
      dba: profile.dba?.trim() || null,
      headcount: typeof profile.headcount === 'number' ? profile.headcount : null,
    };

    const answersPayload = buildGuidedAnswersPayload();
    setGuidedAnswers(answersPayload);

    setGuidedLoading(true);
    try {
      const result = await handbooks.generateGuidedDraft({
        title: title.trim() || null,
        mode,
        scopes,
        profile: normalizedProfile,
        industry,
        answers: answersPayload,
        existing_custom_sections: customSections
          .filter((section) => section.title.trim())
          .map((section, index) => ({
            section_key: `existing_custom_${index + 1}`,
            title: section.title.trim(),
            content: section.content.trim(),
            section_order: 300 + index,
            section_type: 'custom',
            jurisdiction_scope: {},
          })),
      });

      if (result.industry) {
        setIndustry(result.industry);
      }
      setGuidedSummary(result.summary || null);
      setGuidedQuestions(result.questions || []);
      if (result.profile_updates && Object.keys(result.profile_updates).length > 0) {
        setProfile((prev) => ({ ...prev, ...result.profile_updates }));
      }
      mergeSuggestedSections(
        (result.suggested_sections || []).map((section) => ({
          title: section.title,
          content: section.content,
        }))
      );
    } catch (err) {
      setGuidedError(err instanceof Error ? err.message : 'Failed to generate guided draft');
    } finally {
      setGuidedLoading(false);
    }
  };

  const handleSourceFileUpload = async () => {
    if (!file) return;
    try {
      const uploaded = await handbooks.uploadFile(file);
      setUploadedFileUrl(uploaded.url);
      setUploadedFilename(uploaded.filename);
      setFile(null);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to upload file';
      setError(msg);
    }
  };

  const getStepError = (step: number): string | null => {
    if (step === 0) {
      if (!title.trim()) return 'Title is required';
      return null;
    }

    if (step === 1) {
      if (selectedStates.length === 0) return 'Select at least one state';
      if (mode === 'single_state' && selectedStates.length !== 1) return 'Single-state handbooks must have exactly one state';
      if (mode === 'multi_state' && selectedStates.length < 2) return 'Multi-state handbooks require at least two states';
      return null;
    }

    if (step === 2) {
      if (!profile.legal_name?.trim()) return 'Company legal name is required';
      if (!profile.ceo_or_president?.trim()) return 'CEO/President is required';
      return null;
    }

    if (step === 3) {
      if (sourceType === 'upload' && !uploadedFileUrl) return 'Upload a handbook file before continuing';
      return null;
    }

    return null;
  };

  const goToNextStep = () => {
    const err = getStepError(currentStep);
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    setCurrentStep((prev) => Math.min(prev + 1, CREATE_STEPS.length - 1));
  };

  const goToPrevStep = () => {
    setError(null);
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isWizard && currentStep < CREATE_STEPS.length - 1) {
      goToNextStep();
      return;
    }

    const validationError = getStepError(0) || getStepError(1) || getStepError(2) || getStepError(3);
    if (validationError) {
      setError(validationError);
      if (isWizard) {
        if (validationError.includes('Title')) setCurrentStep(0);
        else if (validationError.includes('state')) setCurrentStep(1);
        else if (validationError.includes('CEO') || validationError.includes('legal')) setCurrentStep(2);
        else setCurrentStep(3);
      }
      return;
    }

    try {
      setLoading(true);
      const normalizedSelectedStates = selectedStates.map((state) => state.toUpperCase());
      const locationBackedScopes = buildScopesFromSelectedStates(normalizedSelectedStates);
      const scopes = isEditing
        ? (() => {
            const selectedStateSet = new Set(normalizedSelectedStates);
            const retainedScopes = (existingScopes || [])
              .filter((scope) => selectedStateSet.has((scope.state || '').toUpperCase()))
              .map((scope) => ({
                state: (scope.state || '').toUpperCase(),
                city: scope.city ?? null,
                zipcode: scope.zipcode ?? null,
                location_id: scope.location_id ?? null,
              }));
            const retainedScopeKeys = new Set(
              retainedScopes.map(
                (scope) => `${scope.state}|${scope.city || ''}|${scope.zipcode || ''}|${scope.location_id || ''}`
              )
            );
            const newStateScopes = locationBackedScopes.filter((scope) => {
              const key = `${scope.state}|${scope.city || ''}|${scope.zipcode || ''}|${scope.location_id || ''}`;
              return !retainedScopeKeys.has(key);
            });
            return [...retainedScopes, ...newStateScopes];
          })()
        : locationBackedScopes;

      const normalizedProfile: CompanyHandbookProfile = {
        ...profile,
        legal_name: profile.legal_name?.trim() || '',
        ceo_or_president: profile.ceo_or_president?.trim() || '',
        dba: profile.dba?.trim() || null,
        headcount: typeof profile.headcount === 'number' ? profile.headcount : null,
      };

      if (isEditing && id) {
        await handbooks.update(id, {
          title: title.trim(),
          mode,
          scopes,
          profile: normalizedProfile,
          ...(sourceType === 'upload' ? { file_url: uploadedFileUrl, file_name: uploadedFilename } : {}),
        });
        navigate(`/app/matcha/handbook/${id}`);
      } else {
        const created = await handbooks.create({
          title: title.trim(),
          mode,
          source_type: sourceType,
          industry: sourceType === 'template' ? industry : null,
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

  const renderBasicsStep = () => (
    <>
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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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

        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Source</label>
          {isEditing ? (
            <div className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-zinc-300 text-sm">
              {sourceType === 'template' ? 'Template Builder' : 'Uploaded File'}
            </div>
          ) : (
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as HandbookSourceType)}
              className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
            >
              <option value="template">Template Builder</option>
              <option value="upload">Upload Existing Handbook</option>
            </select>
          )}
        </div>

        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Industry</label>
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
          >
            {INDUSTRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Sub-Industry / Business Model</label>
          <input
            type="text"
            value={subIndustry}
            onChange={(e) => setSubIndustry(e.target.value)}
            placeholder="e.g. SaaS payroll platform, urgent care clinics, franchise restaurants"
            className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-sm focus:outline-none focus:border-white/50"
          />
        </div>
        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Policy Pack Focus</label>
          <div className="min-h-[42px] px-3 py-2 bg-zinc-900 border border-white/20 text-sm text-zinc-200">
            {industryPlaybook.focus}
          </div>
        </div>
      </div>

      {sourceType === 'template' && (
        <div className="space-y-3 border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sparkles size={14} className="text-amber-300" />
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500">
                Business Profile + Policy Pack
              </label>
            </div>
            <button
              type="button"
              onClick={handleGenerateGuidedDraft}
              disabled={guidedLoading}
              className="px-3 py-1.5 bg-white text-black text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
            >
              {guidedLoading ? 'Building...' : guidedSummary ? 'Refresh Policy Pack' : 'Build Policy Pack'}
            </button>
          </div>

          <p className="text-[11px] text-zinc-500">
            Generate boilerplate from your industry + workforce profile, then answer only unresolved follow-up questions.
          </p>
          <p className="text-[11px] text-amber-300/90 border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            Matcha generates state and city compliance boilerplate for the selected scope. Any company-authored culture
            or custom policy language is employer-owned and should be reviewed by your counsel before publication.
          </p>

          <div className="flex flex-wrap gap-2">
            {industryPlaybook.boilerplate.map((item) => (
              <span
                key={item}
                className="px-2 py-1 border border-white/15 bg-zinc-950 text-[10px] uppercase tracking-wider text-zinc-300"
              >
                {item}
              </span>
            ))}
          </div>

          <div className="space-y-2">
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">Quick Business Signals</p>
            <div className="flex flex-wrap gap-2">
              {QUICK_SIGNAL_FIELDS.map((field) => {
                const enabled = Boolean(profile[field.key]);
                return (
                  <button
                    key={field.key}
                    type="button"
                    onClick={() => setProfileField(field.key, !enabled)}
                    className={`px-2 py-1 text-[10px] uppercase tracking-wider border transition-colors ${
                      enabled
                        ? 'bg-emerald-500/20 border-emerald-400/40 text-emerald-200'
                        : 'bg-zinc-950 border-white/20 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {field.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="border-t border-white/10 pt-3 text-[11px] text-zinc-400">
            {guidedQuestions.length > 0 ? (
              <span>
                {answeredGuidedCount}/{guidedQuestions.length} follow-up questions resolved
              </span>
            ) : guidedSummary ? (
              <span>Policy pack generated and sections prefilled.</span>
            ) : (
              <span>No policy pack generated yet.</span>
            )}
          </div>

          {guidedSummary && (
            <p className="text-xs text-zinc-300 leading-relaxed">{guidedSummary}</p>
          )}
          {guidedError && (
            <p className="text-xs text-red-400">{guidedError}</p>
          )}
          {guidedQuestions.length > 0 && (
            <div className="space-y-2 border-t border-white/10 pt-3">
              <p className="text-[10px] uppercase tracking-widest text-zinc-500">Open Follow-up Questions</p>
              {guidedQuestions.map((question) => (
                <div key={question.id} className="space-y-1">
                  <label className="text-xs text-zinc-300">
                    {question.question}
                    {question.required ? <span className="text-amber-400"> *</span> : null}
                  </label>
                  <input
                    type="text"
                    value={guidedAnswers[question.id] || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      setGuidedAnswers((prev) => ({ ...prev, [question.id]: value }));
                    }}
                    placeholder={question.placeholder || 'Add your answer'}
                    className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-xs focus:outline-none focus:border-white/50"
                  />
                </div>
              ))}
              <button
                type="button"
                onClick={handleGenerateGuidedDraft}
                disabled={guidedLoading}
                className="text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider underline underline-offset-4"
              >
                Update pack with answers
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );

  const renderScopeStep = () => (
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
  );

  const renderCompanyStep = () => (
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
  );

  const renderWorkforceStep = () => (
    <>
      <div className="space-y-3">
        <p className="text-[10px] uppercase tracking-widest text-zinc-500">
          Answer each question with Yes or No
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 bg-zinc-900/40 p-4">
        {boolFields.map((field) => (
          <label key={field.key} className="flex items-center justify-between text-xs text-zinc-300">
            <span>{field.label}</span>
            <div className="inline-flex border border-white/20 text-[10px] uppercase tracking-wider">
              <button
                type="button"
                onClick={() => setProfileField(field.key, false)}
                className={`px-2 py-1 transition-colors ${
                  !Boolean(profile[field.key]) ? 'bg-white text-black' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                No
              </button>
              <button
                type="button"
                onClick={() => setProfileField(field.key, true)}
                className={`px-2 py-1 transition-colors ${
                  Boolean(profile[field.key]) ? 'bg-emerald-500 text-white' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Yes
              </button>
            </div>
          </label>
        ))}
        </div>
      </div>

      {sourceType === 'upload' && (
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

      {sourceType === 'template' && (
        <div className="space-y-3 border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500">Custom Company Sections</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerateGuidedDraft}
                disabled={guidedLoading}
                className="px-2 py-1 border border-white/20 text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider disabled:opacity-50"
              >
                {guidedLoading ? 'Updating...' : 'Refresh Pack'}
              </button>
              <button
                type="button"
                onClick={() => setCustomSections((prev) => [...prev, { title: '', content: '' }])}
                className="text-xs text-zinc-300 hover:text-white uppercase tracking-wider flex items-center gap-1"
              >
                <Plus size={12} />
                Add Section
              </button>
            </div>
          </div>
          <p className="text-[11px] text-zinc-500">
            Boilerplate comes from the Business Profile policy pack. Use custom sections for company-specific rules or exceptions.
            {guidedQuestions.length > 0 ? ` ${unansweredGuidedCount} follow-up question(s) still open.` : ''}
          </p>
          <p className="text-[11px] text-amber-300/90 border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            Custom sections are not statutory boilerplate. Your team is legally responsible for custom culture and policy language.
          </p>
          {guidedSummary && (
            <p className="text-xs text-zinc-300 leading-relaxed">{guidedSummary}</p>
          )}
          {guidedError && (
            <p className="text-xs text-red-400">{guidedError}</p>
          )}
          {guidedQuestions.length > 0 && (
            <div className="space-y-2 border border-white/10 bg-zinc-950/60 p-3">
              <p className="text-[10px] uppercase tracking-widest text-zinc-500">Open Follow-up Questions</p>
              {guidedQuestions.map((question) => (
                <div key={question.id} className="space-y-1">
                  <label className="text-xs text-zinc-300">
                    {question.question}
                    {question.required ? <span className="text-amber-400"> *</span> : null}
                  </label>
                  <input
                    type="text"
                    value={guidedAnswers[question.id] || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      setGuidedAnswers((prev) => ({ ...prev, [question.id]: value }));
                    }}
                    placeholder={question.placeholder || 'Add your answer'}
                    className="w-full px-3 py-2 bg-zinc-900 border border-white/20 text-white text-xs focus:outline-none focus:border-white/50"
                  />
                </div>
              ))}
              <button
                type="button"
                onClick={handleGenerateGuidedDraft}
                disabled={guidedLoading}
                className="text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider underline underline-offset-4"
              >
                Apply follow-up answers
              </button>
            </div>
          )}
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
    </>
  );

  const renderReviewStep = () => (
    <div className="border border-white/10 bg-zinc-900/40 p-5 space-y-4">
      <div className="flex items-center gap-2 text-emerald-400 text-sm">
        <CheckCircle2 size={16} />
        Ready to create handbook
      </div>
      <div className="text-xs text-zinc-300 space-y-2">
        <div><span className="text-zinc-500">Title:</span> {title || 'N/A'}</div>
        <div><span className="text-zinc-500">Type:</span> {mode === 'multi_state' ? 'Multi-State' : 'Single-State'}</div>
        <div><span className="text-zinc-500">Source:</span> {sourceType === 'template' ? 'Template Builder' : 'Uploaded File'}</div>
        <div><span className="text-zinc-500">Industry:</span> {selectedIndustryLabel}</div>
        <div><span className="text-zinc-500">Sub-Industry:</span> {subIndustry || 'N/A'}</div>
        <div><span className="text-zinc-500">States:</span> {selectedStates.join(', ') || 'N/A'}</div>
        <div><span className="text-zinc-500">Legal Name:</span> {profile.legal_name || 'N/A'}</div>
        <div><span className="text-zinc-500">CEO/President:</span> {profile.ceo_or_president || 'N/A'}</div>
        <div><span className="text-zinc-500">Headcount:</span> {profile.headcount ?? 'N/A'}</div>
        {sourceType === 'template' && (
          <>
            <div><span className="text-zinc-500">Policy Pack:</span> {guidedSummary ? 'Generated' : 'Not generated yet'}</div>
            <div><span className="text-zinc-500">Open Follow-ups:</span> {guidedQuestions.length > 0 ? unansweredGuidedCount : 0}</div>
          </>
        )}
        {sourceType === 'upload' && (
          <div><span className="text-zinc-500">Uploaded File:</span> {uploadedFilename || 'None'}</div>
        )}
        {sourceType === 'template' && (
          <div><span className="text-zinc-500">Custom Sections:</span> {customSections.filter((s) => s.title.trim()).length}</div>
        )}
        {sourceType === 'template' && (
          <div className="text-amber-300">
            <span className="text-zinc-500">Liability Notice:</span> Matcha supplies state/city boilerplate; custom sections are employer-authored and require your legal review.
          </div>
        )}
      </div>
    </div>
  );

  const renderActiveFormContent = () => {
    if (!isWizard) {
      return (
        <div className="space-y-8">
          {renderBasicsStep()}
          {renderScopeStep()}
          {renderCompanyStep()}
          {renderWorkforceStep()}
        </div>
      );
    }

    if (currentStep === 0) return renderBasicsStep();
    if (currentStep === 1) return renderScopeStep();
    if (currentStep === 2) return renderCompanyStep();
    if (currentStep === 3) return renderWorkforceStep();
    return renderReviewStep();
  };

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
            {isEditing ? 'Update handbook scope and employer settings' : 'Step-by-step handbook setup wizard'}
          </p>
          {isWizard && (
            <div className="mt-3">
              <FeatureGuideTrigger guideId="handbook-create" />
            </div>
          )}
        </div>
      </div>

      {isWizard && (
        <div data-tour="handbook-wizard-progress" className="border border-white/10 bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-zinc-500 mb-3">
            <span>Step {currentStep + 1} of {CREATE_STEPS.length}</span>
            <span>{CREATE_STEPS[currentStep]}</span>
          </div>
          <div className="grid grid-cols-5 gap-2">
            {CREATE_STEPS.map((step, idx) => (
              <button
                key={step}
                type="button"
                onClick={() => setCurrentStep(idx)}
                data-tour={
                  idx === 0
                    ? 'handbook-step-pill-basics'
                    : idx === 1
                    ? 'handbook-step-pill-scope'
                    : idx === 2
                    ? 'handbook-step-pill-profile'
                    : idx === 3
                    ? 'handbook-step-pill-workforce'
                    : 'handbook-step-pill-review'
                }
                className={`h-2 rounded-sm transition-colors ${
                  idx <= currentStep ? 'bg-white' : 'bg-white/15'
                }`}
                aria-label={`Go to ${step}`}
              />
            ))}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {renderActiveFormContent()}

        {error && (
          <div className="text-red-400 text-xs font-medium px-4 py-3 border border-red-500/30 bg-red-500/10 rounded-sm">
            {error}
          </div>
        )}

        <div className="flex justify-between gap-4 pt-6 border-t border-white/10">
          <button
            type="button"
            onClick={isWizard ? (currentStep === 0 ? () => navigate(-1) : goToPrevStep) : () => navigate(-1)}
            className="px-6 py-2 text-zinc-500 hover:text-white text-xs font-medium uppercase tracking-wider transition-colors flex items-center gap-1"
          >
            <ChevronLeft size={12} />
            {isWizard && currentStep > 0 ? 'Previous' : 'Cancel'}
          </button>

          {isWizard ? (
            currentStep < CREATE_STEPS.length - 1 ? (
              <button
                type="button"
                onClick={goToNextStep}
                className="px-8 py-2 bg-white hover:bg-zinc-200 text-black rounded-sm text-xs font-medium uppercase tracking-wider transition-colors flex items-center gap-1"
              >
                Next
                <ChevronRight size={12} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={loading}
                className="px-8 py-2 bg-white hover:bg-zinc-200 text-black rounded-sm text-xs font-medium uppercase tracking-wider transition-colors disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create Handbook'}
              </button>
            )
          ) : (
            <button
              type="submit"
              disabled={loading}
              className="px-8 py-2 bg-white hover:bg-zinc-200 text-black rounded-sm text-xs font-medium uppercase tracking-wider transition-colors disabled:opacity-50"
            >
              {loading ? 'Saving...' : 'Update Handbook'}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

export default HandbookForm;
