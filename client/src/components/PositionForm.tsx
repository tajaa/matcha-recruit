import { useState } from 'react';
import type { PositionCreate, EmploymentType, ExperienceLevel, RemotePolicy, Company } from '../types';
import { Button } from './Button';
import { SkillsInput } from './SkillsInput';

interface PositionFormProps {
  companies: Company[];
  initialCompanyId?: string;
  onSubmit: (data: PositionCreate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

export function PositionForm({
  companies,
  initialCompanyId,
  onSubmit,
  onCancel,
  isLoading = false,
}: PositionFormProps) {
  const [formData, setFormData] = useState<PositionCreate>({
    company_id: initialCompanyId || '',
    title: '',
    salary_min: undefined,
    salary_max: undefined,
    salary_currency: 'USD',
    location: '',
    employment_type: undefined,
    experience_level: undefined,
    remote_policy: undefined,
    required_skills: [],
    preferred_skills: [],
    requirements: [],
    responsibilities: [],
    benefits: [],
    department: '',
    reporting_to: '',
    visa_sponsorship: false,
  });

  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(formData);
  };

  const updateField = <K extends keyof PositionCreate>(field: K, value: PositionCreate[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const inputClass = 'w-full px-4 py-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent';
  const selectClass = 'w-full px-4 py-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent';
  const labelClass = 'block text-sm font-medium text-zinc-400 mb-2';

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Basic Information */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Basic Information</h3>

        <div>
          <label className={labelClass}>Company *</label>
          <select
            value={formData.company_id}
            onChange={e => updateField('company_id', e.target.value)}
            className={selectClass}
            required
          >
            <option value="">Select a company</option>
            {companies.map(company => (
              <option key={company.id} value={company.id}>{company.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelClass}>Job Title *</label>
          <input
            type="text"
            value={formData.title}
            onChange={e => updateField('title', e.target.value)}
            className={inputClass}
            placeholder="e.g., Senior Software Engineer"
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Employment Type</label>
            <select
              value={formData.employment_type || ''}
              onChange={e => updateField('employment_type', (e.target.value || undefined) as EmploymentType | undefined)}
              className={selectClass}
            >
              <option value="">Select type</option>
              <option value="full-time">Full-time</option>
              <option value="part-time">Part-time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
              <option value="temporary">Temporary</option>
            </select>
          </div>

          <div>
            <label className={labelClass}>Experience Level</label>
            <select
              value={formData.experience_level || ''}
              onChange={e => updateField('experience_level', (e.target.value || undefined) as ExperienceLevel | undefined)}
              className={selectClass}
            >
              <option value="">Select level</option>
              <option value="entry">Entry</option>
              <option value="mid">Mid</option>
              <option value="senior">Senior</option>
              <option value="lead">Lead</option>
              <option value="executive">Executive</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Location</label>
            <input
              type="text"
              value={formData.location || ''}
              onChange={e => updateField('location', e.target.value || undefined)}
              className={inputClass}
              placeholder="e.g., San Francisco, CA"
            />
          </div>

          <div>
            <label className={labelClass}>Remote Policy</label>
            <select
              value={formData.remote_policy || ''}
              onChange={e => updateField('remote_policy', (e.target.value || undefined) as RemotePolicy | undefined)}
              className={selectClass}
            >
              <option value="">Select policy</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </div>
        </div>
      </div>

      {/* Compensation */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Compensation</h3>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={labelClass}>Min Salary</label>
            <input
              type="number"
              value={formData.salary_min || ''}
              onChange={e => updateField('salary_min', e.target.value ? parseInt(e.target.value) : undefined)}
              className={inputClass}
              placeholder="80000"
            />
          </div>

          <div>
            <label className={labelClass}>Max Salary</label>
            <input
              type="number"
              value={formData.salary_max || ''}
              onChange={e => updateField('salary_max', e.target.value ? parseInt(e.target.value) : undefined)}
              className={inputClass}
              placeholder="120000"
            />
          </div>

          <div>
            <label className={labelClass}>Currency</label>
            <select
              value={formData.salary_currency || 'USD'}
              onChange={e => updateField('salary_currency', e.target.value)}
              className={selectClass}
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
              <option value="CAD">CAD</option>
              <option value="AUD">AUD</option>
            </select>
          </div>
        </div>
      </div>

      {/* Skills */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Skills</h3>

        <SkillsInput
          label="Required Skills"
          value={formData.required_skills || []}
          onChange={skills => updateField('required_skills', skills)}
          placeholder="Type a skill and press Enter..."
        />

        <SkillsInput
          label="Preferred Skills"
          value={formData.preferred_skills || []}
          onChange={skills => updateField('preferred_skills', skills)}
          placeholder="Type a skill and press Enter..."
        />
      </div>

      {/* Advanced Options Toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-300 transition-colors"
      >
        <svg
          className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {showAdvanced ? 'Hide' : 'Show'} Advanced Options
      </button>

      {/* Advanced Options */}
      {showAdvanced && (
        <div className="space-y-4 pt-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Department</label>
              <input
                type="text"
                value={formData.department || ''}
                onChange={e => updateField('department', e.target.value || undefined)}
                className={inputClass}
                placeholder="e.g., Engineering"
              />
            </div>

            <div>
              <label className={labelClass}>Reports To</label>
              <input
                type="text"
                value={formData.reporting_to || ''}
                onChange={e => updateField('reporting_to', e.target.value || undefined)}
                className={inputClass}
                placeholder="e.g., VP of Engineering"
              />
            </div>
          </div>

          <SkillsInput
            label="Requirements"
            value={formData.requirements || []}
            onChange={reqs => updateField('requirements', reqs)}
            placeholder="Add job requirements..."
          />

          <SkillsInput
            label="Responsibilities"
            value={formData.responsibilities || []}
            onChange={resps => updateField('responsibilities', resps)}
            placeholder="Add job responsibilities..."
          />

          <SkillsInput
            label="Benefits"
            value={formData.benefits || []}
            onChange={benefits => updateField('benefits', benefits)}
            placeholder="Add benefits..."
          />

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="visa_sponsorship"
              checked={formData.visa_sponsorship || false}
              onChange={e => updateField('visa_sponsorship', e.target.checked)}
              className="w-4 h-4 rounded border-zinc-700 bg-zinc-900 text-matcha-500 focus:ring-matcha-500 focus:ring-offset-zinc-950"
            />
            <label htmlFor="visa_sponsorship" className="text-sm text-zinc-300">
              Visa sponsorship available
            </label>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button type="submit" disabled={isLoading || !formData.company_id || !formData.title}>
          {isLoading ? 'Creating...' : 'Create Position'}
        </Button>
      </div>
    </form>
  );
}
