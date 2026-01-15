import { useState, useEffect, useRef, type FormEvent } from 'react';
import { Button } from '../components/Button';
import { ChevronRight, Check, ArrowRight, ArrowLeft, Upload, X } from 'lucide-react';
import { offerLetters as offerLettersApi } from '../api/client';
import type { OfferLetter, OfferLetterCreate } from '../types';

const EMPLOYMENT_TYPES = [
  'Full-Time Exempt',
  'Full-Time Hourly',
  'Part-Time Hourly',
  'Contract',
  'Internship',
] as const;

const initialFormData: OfferLetterCreate = {
  candidate_name: '',
  position_title: '',
  company_name: 'Matcha Tech, Inc.',
  start_date: '',
  salary: '',
  bonus: '',
  stock_options: '',
  employment_type: 'Full-Time Exempt',
  location: '',
  benefits: '',
  manager_name: '',
  manager_title: '',
  expiration_date: '',
  // Structured benefits
  benefits_medical: false,
  benefits_medical_coverage: undefined,
  benefits_medical_waiting_days: 0,
  benefits_dental: false,
  benefits_vision: false,
  benefits_401k: false,
  benefits_401k_match: '',
  benefits_wellness: '',
  benefits_pto_vacation: false,
  benefits_pto_sick: false,
  benefits_holidays: false,
  benefits_other: '',
  // Contingencies
  contingency_background_check: false,
  contingency_credit_check: false,
  contingency_drug_screening: false,
  // Logo
  company_logo_url: '',
};

export function OfferLetters() {
  const [offerLetters, setOfferLetters] = useState<OfferLetter[]>([]);
  const [selectedLetter, setSelectedLetter] = useState<OfferLetter | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Creation Mode State
  const [createMode, setCreateMode] = useState<'form' | 'wizard' | 'select' | null>(null);
  const [wizardStep, setWizardStep] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Logo upload state
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);

  // Form state
  const [formData, setFormData] = useState<OfferLetterCreate>(initialFormData);

  useEffect(() => {
    loadOfferLetters();
  }, []);

  async function loadOfferLetters() {
    try {
      setIsLoading(true);
      const data = await offerLettersApi.list();
      setOfferLetters(data);
    } catch (error) {
      console.error('Failed to load offer letters:', error);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreate(e?: FormEvent) {
    if (e) e.preventDefault();
    if (isSubmitting) return;

    try {
      setIsSubmitting(true);
      const payload = {
        ...formData,
        start_date: formData.start_date || undefined,
        expiration_date: formData.expiration_date || undefined,
      };

      let savedOffer: OfferLetter;
      if (editingId) {
        savedOffer = await offerLettersApi.update(editingId, payload);
      } else {
        savedOffer = await offerLettersApi.create(payload);
      }

      // Upload logo if there's a new file
      if (logoFile) {
        await offerLettersApi.uploadLogo(savedOffer.id, logoFile);
      }

      await loadOfferLetters();
      resetCreation();
    } catch (error) {
      console.error('Failed to create/update offer letter:', error);
    } finally {
      setIsSubmitting(false);
    }
  }

  const resetCreation = () => {
    setCreateMode(null);
    setWizardStep(1);
    setEditingId(null);
    setLogoFile(null);
    setLogoPreview(null);
    setFormData(initialFormData);
  };

  const handleEditDraft = (letter: OfferLetter) => {
    setFormData({
      candidate_name: letter.candidate_name,
      position_title: letter.position_title,
      company_name: letter.company_name,
      salary: letter.salary || '',
      bonus: letter.bonus || '',
      stock_options: letter.stock_options || '',
      start_date: letter.start_date || '',
      employment_type: letter.employment_type || 'Full-Time Exempt',
      location: letter.location || '',
      benefits: letter.benefits || '',
      manager_name: letter.manager_name || '',
      manager_title: letter.manager_title || '',
      expiration_date: letter.expiration_date || '',
      benefits_medical: letter.benefits_medical || false,
      benefits_medical_coverage: letter.benefits_medical_coverage || undefined,
      benefits_medical_waiting_days: letter.benefits_medical_waiting_days || 0,
      benefits_dental: letter.benefits_dental || false,
      benefits_vision: letter.benefits_vision || false,
      benefits_401k: letter.benefits_401k || false,
      benefits_401k_match: letter.benefits_401k_match || '',
      benefits_wellness: letter.benefits_wellness || '',
      benefits_pto_vacation: letter.benefits_pto_vacation || false,
      benefits_pto_sick: letter.benefits_pto_sick || false,
      benefits_holidays: letter.benefits_holidays || false,
      benefits_other: letter.benefits_other || '',
      contingency_background_check: letter.contingency_background_check || false,
      contingency_credit_check: letter.contingency_credit_check || false,
      contingency_drug_screening: letter.contingency_drug_screening || false,
      company_logo_url: letter.company_logo_url || '',
    });
    if (letter.company_logo_url) {
      setLogoPreview(letter.company_logo_url);
    }
    setEditingId(letter.id);
    setSelectedLetter(null);
    setCreateMode('form');
  };

  const handleDownloadPdf = async (letter: OfferLetter) => {
    try {
      await offerLettersApi.downloadPdf(letter.id, letter.candidate_name);
    } catch (error) {
      console.error('Failed to download PDF:', error);
    }
  };

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setLogoFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setLogoPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const removeLogo = () => {
    setLogoFile(null);
    setLogoPreview(null);
    setFormData({ ...formData, company_logo_url: '' });
    if (logoInputRef.current) {
      logoInputRef.current.value = '';
    }
  };

  // Helper to generate benefits text for preview
  const generateBenefitsText = (letter: OfferLetter): string => {
    const parts: string[] = [];

    if (letter.benefits_medical) {
      let medical = 'medical insurance';
      if (letter.benefits_medical_coverage) {
        medical += ` (employer covers ${letter.benefits_medical_coverage}% of premiums)`;
      }
      if (letter.benefits_medical_waiting_days && letter.benefits_medical_waiting_days > 0) {
        medical += ` after a ${letter.benefits_medical_waiting_days}-day waiting period`;
      }
      parts.push(medical);
    }
    if (letter.benefits_dental) parts.push('dental insurance');
    if (letter.benefits_vision) parts.push('vision insurance');
    if (letter.benefits_401k) {
      let k401 = '401(k) retirement plan';
      if (letter.benefits_401k_match) k401 += ` with ${letter.benefits_401k_match}`;
      parts.push(k401);
    }
    if (letter.benefits_wellness) parts.push(`wellness benefits (${letter.benefits_wellness})`);
    if (letter.benefits_pto_vacation || letter.benefits_pto_sick) {
      const ptoParts: string[] = [];
      if (letter.benefits_pto_vacation) ptoParts.push('vacation');
      if (letter.benefits_pto_sick) ptoParts.push('sick leave');
      parts.push(`paid time off (${ptoParts.join(' and ')})`);
    }
    if (letter.benefits_holidays) parts.push('paid holidays');
    if (letter.benefits_other) parts.push(letter.benefits_other);

    if (parts.length === 0) return '';
    if (parts.length === 1) return `You will be eligible for ${parts[0]}.`;
    if (parts.length === 2) return `You will be eligible for ${parts[0]} and ${parts[1]}.`;
    return `You will be eligible for ${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}.`;
  };

  // Helper to generate contingencies text for preview
  const generateContingenciesText = (letter: OfferLetter): string => {
    const contingencies: string[] = [];
    if (letter.contingency_background_check) contingencies.push('background check');
    if (letter.contingency_credit_check) contingencies.push('credit check');
    if (letter.contingency_drug_screening) contingencies.push('drug screening');

    const base = 'This offer of employment is contingent upon your authorization to work in the United States, as required by federal law.';
    if (contingencies.length === 0) return base;

    let list: string;
    if (contingencies.length === 1) list = contingencies[0];
    else if (contingencies.length === 2) list = `${contingencies[0]} and ${contingencies[1]}`;
    else list = `${contingencies.slice(0, -1).join(', ')}, and ${contingencies[contingencies.length - 1]}`;

    return `${base} This offer is also contingent upon the successful completion of the following: ${list}.`;
  };

  const statusColors: Record<string, string> = {
    draft: 'text-zinc-500',
    sent: 'text-blue-600',
    accepted: 'text-emerald-600',
    rejected: 'text-red-600',
    expired: 'text-zinc-400',
  };

  const statusDotColors: Record<string, string> = {
    draft: 'bg-zinc-400',
    sent: 'bg-blue-500',
    accepted: 'bg-emerald-500',
    rejected: 'bg-red-500',
    expired: 'bg-zinc-300',
  };

  // Wizard Steps Components
  const renderWizardStep = () => {
    switch (wizardStep) {
      case 1: // Basics
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className="text-sm font-medium text-zinc-900 mb-4">Who are we hiring?</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Candidate Name</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="Enter full name"
                  value={formData.candidate_name}
                  onChange={(e) => setFormData({...formData, candidate_name: e.target.value})}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Role Title</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. Senior Engineer"
                  value={formData.position_title}
                  onChange={(e) => setFormData({...formData, position_title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Start Date</label>
                <input
                  type="date"
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                  value={formData.start_date ? new Date(formData.start_date).toISOString().split('T')[0] : ''}
                  onChange={(e) => setFormData({...formData, start_date: e.target.value})}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Company Logo (optional)</label>
                <input type="file" ref={logoInputRef} accept="image/*" onChange={handleLogoChange} className="hidden" />
                {logoPreview ? (
                  <div className="flex items-center gap-4 p-3 bg-zinc-50 border border-zinc-200 rounded">
                    <img src={logoPreview} alt="Logo preview" className="h-10 max-w-[120px] object-contain" />
                    <button type="button" onClick={removeLogo} className="text-xs text-red-600 hover:text-red-700 flex items-center gap-1">
                      <X size={14} /> Remove
                    </button>
                  </div>
                ) : (
                  <button type="button" onClick={() => logoInputRef.current?.click()} className="w-full flex items-center justify-center gap-2 px-4 py-3 border border-dashed border-zinc-300 text-sm text-zinc-500 hover:border-zinc-400 hover:text-zinc-600 transition-colors rounded">
                    <Upload size={16} />
                    Upload company logo
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      case 2: // Compensation
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className="text-sm font-medium text-zinc-900 mb-4">Compensation Package</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Annual Salary</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. $150,000"
                  value={formData.salary || ''}
                  onChange={(e) => setFormData({...formData, salary: e.target.value})}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Bonus Potential</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. 15% Annual"
                  value={formData.bonus || ''}
                  onChange={(e) => setFormData({...formData, bonus: e.target.value})}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Equity / Options</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. 5,000 RSUs"
                  value={formData.stock_options || ''}
                  onChange={(e) => setFormData({...formData, stock_options: e.target.value})}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Employment Type</label>
                <select
                    className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                    value={formData.employment_type || 'Full-Time Exempt'}
                    onChange={(e) => setFormData({...formData, employment_type: e.target.value})}
                >
                    {EMPLOYMENT_TYPES.map(type => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                </select>
              </div>
            </div>
          </div>
        );
      case 3: // Reporting
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className="text-sm font-medium text-zinc-900 mb-4">Reporting & Location</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Name</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. David Chen"
                  value={formData.manager_name || ''}
                  onChange={(e) => setFormData({...formData, manager_name: e.target.value})}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Title</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. VP of Engineering"
                  value={formData.manager_title || ''}
                  onChange={(e) => setFormData({...formData, manager_title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Location</label>
                <input 
                  type="text" 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                  placeholder="e.g. San Francisco, CA (Hybrid)"
                  value={formData.location || ''}
                  onChange={(e) => setFormData({...formData, location: e.target.value})}
                />
              </div>
            </div>
          </div>
        );
      case 4: // Benefits & Contingencies
        return (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <div>
              <h3 className="text-sm font-medium text-zinc-900 mb-4">Benefits Package</h3>
              <div className="space-y-3">
                {/* Medical */}
                <div className="p-3 bg-zinc-50 border border-zinc-200 rounded">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_medical || false}
                      onChange={(e) => setFormData({...formData, benefits_medical: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-900">Medical insurance offered</span>
                  </label>
                  {formData.benefits_medical && (
                    <div className="mt-3 pl-6 grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase text-zinc-500 mb-1">Employer Coverage %</label>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          placeholder="e.g. 80"
                          className="w-full px-2 py-1.5 bg-white border border-zinc-200 text-sm rounded"
                          value={formData.benefits_medical_coverage || ''}
                          onChange={(e) => setFormData({...formData, benefits_medical_coverage: e.target.value ? parseInt(e.target.value) : undefined})}
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase text-zinc-500 mb-1">Waiting Period</label>
                        <select
                          className="w-full px-2 py-1.5 bg-white border border-zinc-200 text-sm rounded"
                          value={formData.benefits_medical_waiting_days || 0}
                          onChange={(e) => setFormData({...formData, benefits_medical_waiting_days: parseInt(e.target.value)})}
                        >
                          <option value={0}>No waiting period</option>
                          <option value={30}>30 days</option>
                          <option value={60}>60 days</option>
                          <option value={90}>90 days</option>
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                {/* Dental & Vision */}
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_dental || false}
                      onChange={(e) => setFormData({...formData, benefits_dental: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-700">Dental insurance</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_vision || false}
                      onChange={(e) => setFormData({...formData, benefits_vision: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-700">Vision insurance</span>
                  </label>
                </div>

                {/* 401k */}
                <div className="p-3 bg-zinc-50 border border-zinc-200 rounded">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_401k || false}
                      onChange={(e) => setFormData({...formData, benefits_401k: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-900">401(k) retirement plan</span>
                  </label>
                  {formData.benefits_401k && (
                    <div className="mt-3 pl-6">
                      <label className="block text-[10px] uppercase text-zinc-500 mb-1">Employer Match (optional)</label>
                      <input
                        type="text"
                        placeholder="e.g. 4% match up to 6%"
                        className="w-full px-2 py-1.5 bg-white border border-zinc-200 text-sm rounded"
                        value={formData.benefits_401k_match || ''}
                        onChange={(e) => setFormData({...formData, benefits_401k_match: e.target.value})}
                      />
                    </div>
                  )}
                </div>

                {/* Wellness */}
                <div>
                  <label className="block text-[10px] uppercase text-zinc-500 mb-1">Wellness Benefits (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. gym membership, mental health stipend"
                    className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-sm focus:bg-white focus:border-zinc-400 transition-colors"
                    value={formData.benefits_wellness || ''}
                    onChange={(e) => setFormData({...formData, benefits_wellness: e.target.value})}
                  />
                </div>

                {/* PTO */}
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_pto_vacation || false}
                      onChange={(e) => setFormData({...formData, benefits_pto_vacation: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-700">Paid vacation</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_pto_sick || false}
                      onChange={(e) => setFormData({...formData, benefits_pto_sick: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-700">Paid sick leave</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.benefits_holidays || false}
                      onChange={(e) => setFormData({...formData, benefits_holidays: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-300"
                    />
                    <span className="text-sm text-zinc-700">Paid holidays</span>
                  </label>
                </div>

                {/* Other */}
                <div>
                  <label className="block text-[10px] uppercase text-zinc-500 mb-1">Other Benefits (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. parking, commuter benefits"
                    className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-sm focus:bg-white focus:border-zinc-400 transition-colors"
                    value={formData.benefits_other || ''}
                    onChange={(e) => setFormData({...formData, benefits_other: e.target.value})}
                  />
                </div>
              </div>
            </div>

            {/* Contingencies */}
            <div>
              <h3 className="text-sm font-medium text-zinc-900 mb-2">Offer Contingencies</h3>
              <p className="text-xs text-zinc-500 mb-3">I-9 employment verification is always required</p>
              <div className="flex gap-4 flex-wrap">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.contingency_background_check || false}
                    onChange={(e) => setFormData({...formData, contingency_background_check: e.target.checked})}
                    className="w-4 h-4 rounded border-zinc-300"
                  />
                  <span className="text-sm text-zinc-700">Background check</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.contingency_credit_check || false}
                    onChange={(e) => setFormData({...formData, contingency_credit_check: e.target.checked})}
                    className="w-4 h-4 rounded border-zinc-300"
                  />
                  <span className="text-sm text-zinc-700">Credit check</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.contingency_drug_screening || false}
                    onChange={(e) => setFormData({...formData, contingency_drug_screening: e.target.checked})}
                    className="w-4 h-4 rounded border-zinc-300"
                  />
                  <span className="text-sm text-zinc-700">Drug screening</span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Offer Expiration Date</label>
              <input
                type="date"
                className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                value={formData.expiration_date ? new Date(formData.expiration_date).toISOString().split('T')[0] : ''}
                onChange={(e) => setFormData({...formData, expiration_date: e.target.value})}
              />
            </div>
          </div>
        );
      case 5: // Review
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className="text-sm font-medium text-zinc-900 mb-4">Review Offer</h3>
            <div className="bg-zinc-50 border border-zinc-200 rounded p-4 text-sm space-y-3">
              <div className="flex justify-between border-b border-zinc-200 pb-2">
                <span className="text-zinc-500">Candidate</span>
                <span className="font-medium text-zinc-900">{formData.candidate_name}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-200 pb-2">
                <span className="text-zinc-500">Role</span>
                <span className="font-medium text-zinc-900">{formData.position_title}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-200 pb-2">
                <span className="text-zinc-500">Salary</span>
                <span className="font-medium text-zinc-900">{formData.salary}</span>
              </div>
              <div className="flex justify-between border-b border-zinc-200 pb-2">
                <span className="text-zinc-500">Start Date</span>
                <span className="font-medium text-zinc-900">{formData.start_date ? new Date(formData.start_date).toLocaleDateString() : 'TBD'}</span>
              </div>
              <div className="pt-2">
                <p className="text-zinc-500 mb-1 text-xs uppercase tracking-wide">Benefits</p>
                <p className="text-zinc-700">{formData.benefits || 'Standard benefits'}</p>
              </div>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-12">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">Offer Letters</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Manage & Generate Candidate Offers</p>
        </div>
        <div className="relative">
          <button
            onClick={() => setCreateMode(createMode ? null : 'select')} // Toggle selection mode
            className="px-4 py-2 bg-zinc-900 text-white text-xs font-medium hover:bg-zinc-800 uppercase tracking-wider transition-colors"
          >
            Create Offer
          </button>
          
          {/* Mode Selection Dropdown */}
          {createMode === 'select' && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setCreateMode(null)} />
              <div className="absolute right-0 top-full mt-2 w-48 bg-white border border-zinc-200 shadow-xl rounded-sm z-20 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                <button 
                  onClick={() => setCreateMode('form')}
                  className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors border-b border-zinc-100"
                >
                  <span className="block text-xs font-bold text-zinc-900 uppercase tracking-wide">Quick Form</span>
                  <span className="block text-[10px] text-zinc-500 mt-0.5">All fields in one view</span>
                </button>
                <button 
                  onClick={() => setCreateMode('wizard')}
                  className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors"
                >
                  <span className="block text-xs font-bold text-zinc-900 uppercase tracking-wide">Wizard Mode</span>
                  <span className="block text-[10px] text-zinc-500 mt-0.5">Step-by-step guidance</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
           <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading...</div>
        </div>
      ) : offerLetters.length === 0 ? (
        <div className="text-center py-16 border-t border-zinc-200">
          <div className="text-xs text-zinc-500 mb-4">No offer letters generated</div>
          <button
            onClick={() => setCreateMode('wizard')}
            className="text-xs text-zinc-900 hover:text-zinc-700 font-medium uppercase tracking-wider"
          >
            Create your first offer
          </button>
        </div>
      ) : (
        <div className="space-y-1">
           {/* List Header */}
           <div className="flex items-center gap-4 py-2 text-[10px] text-zinc-500 uppercase tracking-wider border-b border-zinc-200">
             <div className="w-8"></div>
             <div className="flex-1">Candidate</div>
             <div className="w-48">Position</div>
             <div className="w-32">Status</div>
             <div className="w-32 text-right">Created</div>
             <div className="w-8"></div>
           </div>

          {offerLetters.map((letter) => (
            <div 
              key={letter.id} 
              className="group flex items-center gap-4 py-4 cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 transition-colors"
              onClick={() => setSelectedLetter(letter)}
            >
              <div className="w-8 flex justify-center">
                 <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[letter.status] || 'bg-zinc-300'}`} />
              </div>
              
              <div className="flex-1">
                 <h3 className="text-sm font-medium text-zinc-900 group-hover:text-zinc-700">
                   {letter.candidate_name}
                 </h3>
                 <p className="text-xs text-zinc-500 mt-0.5">{letter.company_name}</p>
              </div>

              <div className="w-48 text-xs text-zinc-600">
                 {letter.position_title}
              </div>

              <div className={`w-32 text-xs font-medium ${statusColors[letter.status] || 'text-zinc-500'} uppercase tracking-wide text-[10px]`}>
                 {letter.status}
              </div>

              <div className="w-32 text-right text-xs text-zinc-500 font-mono">
                 {new Date(letter.created_at).toLocaleDateString()}
              </div>
              
              <div className="w-8 flex justify-center text-zinc-400 group-hover:text-zinc-600">
                 <ChevronRight className="w-4 h-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal (Form or Wizard) */}
      {(createMode === 'form' || createMode === 'wizard') && (
         <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4">
            <div className="w-full max-w-2xl max-h-[90vh] bg-white shadow-2xl rounded-sm flex flex-col">
               <div className="flex items-center justify-between p-6 border-b border-zinc-100">
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-light text-zinc-900">
                      {createMode === 'wizard' ? `Step ${wizardStep} of 5` : 'Create Offer Letter'}
                    </h2>
                    {createMode === 'wizard' && (
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map(step => (
                          <div 
                            key={step} 
                            className={`w-1.5 h-1.5 rounded-full ${step <= wizardStep ? 'bg-zinc-900' : 'bg-zinc-200'}`}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <button onClick={resetCreation} className="text-zinc-400 hover:text-zinc-600 transition-colors">
                     <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                     </svg>
                  </button>
               </div>
               
               <div className="flex-1 overflow-y-auto p-8">
                {createMode === 'wizard' ? (
                  renderWizardStep()
                ) : (
                  <form className="space-y-8" id="quick-form" onSubmit={handleCreate}>
                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Candidate & Role</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Candidate Name</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="Enter full name"
                              value={formData.candidate_name}
                              onChange={(e) => setFormData({...formData, candidate_name: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Role Title</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. Senior Engineer"
                              value={formData.position_title}
                              onChange={(e) => setFormData({...formData, position_title: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Start Date</label>
                            <input 
                              type="date" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                              value={formData.start_date ? new Date(formData.start_date).toISOString().split('T')[0] : ''}
                              onChange={(e) => setFormData({...formData, start_date: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Expiration Date</label>
                            <input 
                              type="date" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                              value={formData.expiration_date ? new Date(formData.expiration_date).toISOString().split('T')[0] : ''}
                              onChange={(e) => setFormData({...formData, expiration_date: e.target.value})}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Compensation</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Annual Salary</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. $150,000"
                              value={formData.salary || ''}
                              onChange={(e) => setFormData({...formData, salary: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Bonus Potential</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. 15% Annual"
                              value={formData.bonus || ''}
                              onChange={(e) => setFormData({...formData, bonus: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Equity / Options</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. 5,000 RSUs"
                              value={formData.stock_options || ''}
                              onChange={(e) => setFormData({...formData, stock_options: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Employment Type</label>
                            <select
                                className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                                value={formData.employment_type || 'Full-Time Exempt'}
                                onChange={(e) => setFormData({...formData, employment_type: e.target.value})}
                            >
                                {EMPLOYMENT_TYPES.map(type => (
                                  <option key={type} value={type}>{type}</option>
                                ))}
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Reporting & Location</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Name</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. David Chen"
                              value={formData.manager_name || ''}
                              onChange={(e) => setFormData({...formData, manager_name: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Title</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. VP of Engineering"
                              value={formData.manager_title || ''}
                              onChange={(e) => setFormData({...formData, manager_title: e.target.value})}
                            />
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Location</label>
                            <input 
                              type="text" 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                              placeholder="e.g. San Francisco, CA (Hybrid)"
                              value={formData.location || ''}
                              onChange={(e) => setFormData({...formData, location: e.target.value})}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Benefits Package</h3>
                        <div className="grid grid-cols-2 gap-4">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_medical || false} onChange={(e) => setFormData({...formData, benefits_medical: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Medical insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_dental || false} onChange={(e) => setFormData({...formData, benefits_dental: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Dental insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_vision || false} onChange={(e) => setFormData({...formData, benefits_vision: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Vision insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_401k || false} onChange={(e) => setFormData({...formData, benefits_401k: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">401(k)</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_pto_vacation || false} onChange={(e) => setFormData({...formData, benefits_pto_vacation: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Paid vacation</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_pto_sick || false} onChange={(e) => setFormData({...formData, benefits_pto_sick: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Paid sick leave</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.benefits_holidays || false} onChange={(e) => setFormData({...formData, benefits_holidays: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Paid holidays</span>
                          </label>
                        </div>
                        {formData.benefits_medical && (
                          <div className="grid grid-cols-2 gap-4 pl-4 border-l-2 border-zinc-200">
                            <div>
                              <label className="block text-[10px] uppercase text-zinc-500 mb-1">Medical Coverage %</label>
                              <input type="number" min="0" max="100" placeholder="e.g. 80" className="w-full px-2 py-1.5 bg-zinc-50 border border-zinc-200 text-sm" value={formData.benefits_medical_coverage || ''} onChange={(e) => setFormData({...formData, benefits_medical_coverage: e.target.value ? parseInt(e.target.value) : undefined})} />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase text-zinc-500 mb-1">Waiting Period</label>
                              <select className="w-full px-2 py-1.5 bg-zinc-50 border border-zinc-200 text-sm" value={formData.benefits_medical_waiting_days || 0} onChange={(e) => setFormData({...formData, benefits_medical_waiting_days: parseInt(e.target.value)})}>
                                <option value={0}>No waiting</option>
                                <option value={30}>30 days</option>
                                <option value={60}>60 days</option>
                                <option value={90}>90 days</option>
                              </select>
                            </div>
                          </div>
                        )}
                        {formData.benefits_401k && (
                          <div className="pl-4 border-l-2 border-zinc-200">
                            <label className="block text-[10px] uppercase text-zinc-500 mb-1">401(k) Match</label>
                            <input type="text" placeholder="e.g. 4% match" className="w-full px-2 py-1.5 bg-zinc-50 border border-zinc-200 text-sm" value={formData.benefits_401k_match || ''} onChange={(e) => setFormData({...formData, benefits_401k_match: e.target.value})} />
                          </div>
                        )}
                        <div>
                          <label className="block text-[10px] uppercase text-zinc-500 mb-1">Other Benefits</label>
                          <input type="text" placeholder="e.g. wellness stipend, parking" className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-sm" value={formData.benefits_other || ''} onChange={(e) => setFormData({...formData, benefits_other: e.target.value})} />
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Contingencies</h3>
                        <p className="text-xs text-zinc-500">I-9 verification is always required</p>
                        <div className="flex gap-6">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.contingency_background_check || false} onChange={(e) => setFormData({...formData, contingency_background_check: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Background check</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.contingency_credit_check || false} onChange={(e) => setFormData({...formData, contingency_credit_check: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Credit check</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.contingency_drug_screening || false} onChange={(e) => setFormData({...formData, contingency_drug_screening: e.target.checked})} className="w-4 h-4" />
                            <span className="text-sm">Drug screening</span>
                          </label>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Company Logo</h3>
                        <div>
                          <input type="file" ref={logoInputRef} accept="image/*" onChange={handleLogoChange} className="hidden" />
                          {logoPreview ? (
                            <div className="flex items-center gap-4">
                              <img src={logoPreview} alt="Logo preview" className="h-12 max-w-[150px] object-contain" />
                              <button type="button" onClick={removeLogo} className="text-xs text-red-600 hover:text-red-700">Remove</button>
                            </div>
                          ) : (
                            <button type="button" onClick={() => logoInputRef.current?.click()} className="flex items-center gap-2 px-4 py-2 border border-dashed border-zinc-300 text-sm text-zinc-600 hover:border-zinc-400 hover:text-zinc-700 transition-colors">
                              <Upload size={16} />
                              Upload company logo
                            </button>
                          )}
                        </div>
                      </div>
                  </form>
                )}
               </div>

               <div className="flex items-center justify-between p-6 border-t border-zinc-100 bg-zinc-50/30">
                  <Button variant="secondary" type="button" onClick={resetCreation}>Cancel</Button>
                  
                  {createMode === 'wizard' ? (
                    <div className="flex gap-2">
                      {wizardStep > 1 && (
                        <Button variant="secondary" onClick={() => setWizardStep(wizardStep - 1)}>
                          <ArrowLeft size={14} className="mr-2" /> Back
                        </Button>
                      )}
                      {wizardStep < 5 ? (
                        <Button onClick={() => setWizardStep(wizardStep + 1)} className="bg-zinc-900 text-white hover:bg-zinc-800">
                          Next <ArrowRight size={14} className="ml-2" />
                        </Button>
                      ) : (
                        <Button onClick={() => handleCreate()} disabled={isSubmitting} className="bg-zinc-900 text-white hover:bg-zinc-800">
                          {isSubmitting ? 'Generating...' : 'Generate Offer'} <Check size={14} className="ml-2" />
                        </Button>
                      )}
                    </div>
                  ) : (
                    <Button type="submit" form="quick-form" disabled={isSubmitting} className="bg-zinc-900 text-white hover:bg-zinc-800">
                      {isSubmitting ? 'Generating...' : 'Generate Offer'}
                    </Button>
                  )}
               </div>
            </div>
         </div>
      )}

      {/* Detail Modal (Existing View Logic) */}
      {selectedLetter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col bg-white shadow-2xl rounded-sm overflow-hidden">
             {/* Modal Header */}
             <div className="p-6 border-b border-zinc-100 flex items-center justify-between bg-zinc-50/50">
                <div>
                   <h2 className="text-xl font-light text-zinc-900">Offer Details</h2>
                   <p className="text-xs text-zinc-500 mt-1 font-mono uppercase tracking-wide">{selectedLetter.id}</p>
                </div>
                <div className="flex items-center gap-4">
                   <span className={`px-2 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium ${statusColors[selectedLetter.status]} bg-zinc-100`}>
                      {selectedLetter.status}
                   </span>
                   <button
                    onClick={() => setSelectedLetter(null)}
                    className="p-2 hover:bg-zinc-100 rounded-full transition-colors text-zinc-400 hover:text-zinc-600"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
             </div>

             {/* Modal Content */}
             <div className="flex-1 overflow-y-auto p-8 bg-zinc-50/30">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                   {/* Left Sidebar: Metadata */}
                   <div className="space-y-6">
                      <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Candidate</label>
                         <p className="text-zinc-900 font-medium">{selectedLetter.candidate_name}</p>
                      </div>
                      <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Position</label>
                         <p className="text-zinc-700">{selectedLetter.position_title}</p>
                      </div>
                       <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Company</label>
                         <p className="text-zinc-700">{selectedLetter.company_name}</p>
                      </div>
                      
                      <div className="pt-6 border-t border-zinc-200 space-y-3">
                         <Button variant="secondary" className="w-full justify-center" onClick={() => handleDownloadPdf(selectedLetter)}>Download PDF</Button>
                         {selectedLetter.status === 'draft' && (
                           <Button variant="secondary" className="w-full justify-center" onClick={() => handleEditDraft(selectedLetter)}>Edit Draft</Button>
                         )}
                      </div>
                   </div>

                   {/* Right Content: Preview */}
                   <div className="lg:col-span-2">
                      <div className="bg-white border border-zinc-200 shadow-sm p-12 text-zinc-900 font-serif min-h-[600px] text-[13px] leading-relaxed">
                         <div className="space-y-8">
                            <div className="flex justify-between items-start border-b border-zinc-100 pb-6">
                              <div>
                                {selectedLetter.company_logo_url && (
                                  <img src={selectedLetter.company_logo_url} alt="Company logo" className="h-10 max-w-[150px] object-contain mb-2" />
                                )}
                                <h3 className="font-bold text-lg tracking-tight mb-1">{selectedLetter.company_name}</h3>
                                <p className="text-zinc-400 font-sans text-[10px] uppercase tracking-widest">Official Offer of Employment</p>
                              </div>
                              <div className="text-right">
                                  <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest mb-1">Date</p>
                                  <p className="font-bold">{new Date(selectedLetter.created_at).toLocaleDateString()}</p>
                              </div>
                            </div>

                            <div className="space-y-4">
                              <p>Dear <span className="font-bold">{selectedLetter.candidate_name}</span>,</p>

                              <p>
                                We are pleased to offer you the position of <span className="font-bold">{selectedLetter.position_title}</span> at <span className="font-bold">{selectedLetter.company_name}</span>.
                                We were very impressed with your background and believe your skills and experience will be a valuable addition to our team.
                              </p>

                              <p>
                                Should you accept this offer, you will report to <span className="font-bold">{selectedLetter.manager_name || 'the Hiring Manager'}</span>
                                {selectedLetter.manager_title && <span>, {selectedLetter.manager_title}</span>}.
                              </p>

                              {/* Terms Grid */}
                              <div className="bg-zinc-50 p-6 rounded border border-zinc-100 space-y-4 font-sans mt-6 mb-6">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 border-b border-zinc-200 pb-2">Compensation & Terms</h4>
                                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Annual Salary</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.salary || 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Start Date</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.start_date ? new Date(selectedLetter.start_date).toLocaleDateString() : 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Bonus Potential</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.bonus || 'N/A'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Equity / Options</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.stock_options || 'N/A'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Employment Type</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.employment_type || 'Full-Time Exempt'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Location</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.location || 'Remote'}</p>
                                  </div>
                                </div>
                              </div>

                              {/* Benefits Section */}
                              <div className="space-y-2">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 font-sans">Benefits</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  {generateBenefitsText(selectedLetter) || 'Standard company benefits package.'}
                                </p>
                              </div>

                              {/* Contingencies Section */}
                              <div className="space-y-2">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 font-sans">Contingencies</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  {generateContingenciesText(selectedLetter)}
                                </p>
                              </div>

                              {/* At-Will Employment */}
                              <div className="space-y-2 mt-6">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 font-sans">At-Will Employment</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  Your employment with the Company will be on an at-will basis. This means that either you or the Company may terminate the employment relationship at any time, with or without cause or notice, subject to applicable law. Nothing in this offer letter or in any other Company document or policy should be interpreted as creating a contract of employment for any definite period of time.
                                </p>
                              </div>

                              {/* Accept-By Date */}
                              {selectedLetter.expiration_date && (
                                <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded">
                                  <p className="text-amber-800 text-xs">
                                    Please sign and return this offer by <span className="font-bold">{new Date(selectedLetter.expiration_date).toLocaleDateString()}</span>. If the offer is not accepted by this date, it may be withdrawn.
                                  </p>
                                </div>
                              )}
                            </div>

                            {/* Signature Section */}
                            <div className="mt-16 pt-8 border-t border-zinc-100 flex justify-between items-end">
                              <div>
                                <div className="w-48 h-px bg-zinc-300 mb-2"></div>
                                <p className="font-bold text-zinc-900">{selectedLetter.manager_name || 'Hiring Manager'}</p>
                                <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest">Authorized Signature</p>
                              </div>
                              <div className="text-right">
                                  <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest mb-1">Candidate Acceptance</p>
                                  <div className="w-48 h-10 border-b border-dashed border-zinc-300 mb-1"></div>
                              </div>
                            </div>
                         </div>
                      </div>
                   </div>
                </div>
             </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default OfferLetters;