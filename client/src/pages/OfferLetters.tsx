import { useState } from 'react';
import { Button } from '../components/Button';
import { ChevronRight, ChevronDown, Check, ArrowRight, ArrowLeft, Upload, X } from 'lucide-react';
import { offerLetters as offerLettersApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { OfferLetter } from '../types';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { useOfferLetters, useOfferForm, useOfferGuidance, useRangeNegotiation, OFFER_GUIDANCE_CITY_OPTIONS } from '../hooks/offer-letters';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl border border-stone-200',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  btnSecondaryActive: 'border-stone-400 text-zinc-900 bg-stone-200',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  dropdownBg: 'bg-stone-100 border border-stone-200 shadow-xl',
  dropdownItem: 'text-stone-600 hover:bg-stone-50 hover:text-zinc-900',
  rowHover: 'hover:bg-stone-50',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100 rounded-2xl',
  wizardActive: 'border-zinc-900 text-zinc-50 bg-zinc-900',
  wizardInactive: 'border-stone-300 text-stone-400',
  separator: 'bg-stone-300',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'text-stone-500 hover:text-zinc-900',
  chevron: 'text-stone-400 group-hover:text-stone-600',
  tableHeader: 'bg-stone-200 text-stone-500',
  checkboxCls: 'w-4 h-4 rounded border-stone-300 bg-white checked:bg-zinc-900 checked:border-zinc-900',
  reviewBlock: 'bg-stone-200/60 rounded-xl border border-stone-200 p-4 text-sm space-y-3',
  reviewDivide: 'border-b border-stone-200 pb-2',
  statusBadgeBg: 'bg-stone-200 border border-stone-200',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 rounded-2xl border border-white/10',
  innerEl: 'bg-zinc-800/60 rounded-xl border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  divide: 'divide-white/10',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  btnSecondaryActive: 'border-white/20 text-zinc-100 bg-zinc-800',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  dropdownBg: 'bg-zinc-900 border border-white/10 shadow-xl',
  dropdownItem: 'text-zinc-400 hover:bg-white/5 hover:text-zinc-100',
  rowHover: 'hover:bg-white/5',
  emptyBorder: 'border border-dashed border-white/10 bg-zinc-900/30 rounded-2xl',
  wizardActive: 'border-zinc-100 text-zinc-900 bg-zinc-100',
  wizardInactive: 'border-zinc-700 text-zinc-600',
  separator: 'bg-zinc-700',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'text-zinc-500 hover:text-zinc-100',
  chevron: 'text-zinc-600 group-hover:text-zinc-400',
  tableHeader: 'bg-zinc-800 text-zinc-500',
  checkboxCls: 'w-4 h-4 rounded border-white/10 bg-zinc-800 checked:bg-zinc-100 checked:border-zinc-100',
  reviewBlock: 'bg-zinc-800/60 rounded-xl border border-white/10 p-4 text-sm space-y-3',
  reviewDivide: 'border-b border-white/10 pb-2',
  statusBadgeBg: 'bg-zinc-800 border border-white/10',
} as const;

const EMPLOYMENT_TYPES = [
  'Full-Time Exempt',
  'Full-Time Hourly',
  'Part-Time Hourly',
  'Contract',
  'Internship',
] as const;

function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

const OFFER_CYCLE_STEPS = [
  {
    id: 1,
    icon: 'draft' as const,
    title: 'Draft Package',
    description: 'Define the candidate details, position, compensation, and reporting structure.',
    action: 'Click "Create Offer" and choose Wizard or Quick Form.',
  },
  {
    id: 2,
    icon: 'generate' as const,
    title: 'Generate Document',
    description: 'Review the package and generate a professional PDF with your company logo and terms.',
    action: 'Complete the form and click "Generate Offer".',
  },
  {
    id: 3,
    icon: 'send' as const,
    title: 'Send to Candidate',
    description: 'Issue the offer to the candidate via email or provide them a direct portal link.',
    action: 'Download the PDF or use the status tracker to issue.',
  },
  {
    id: 4,
    icon: 'track' as const,
    title: 'Track Status',
    description: 'Monitor whether the offer is pending, accepted, or rejected in real-time.',
    action: 'Watch the status labels in the list view below.',
  },
  {
    id: 5,
    icon: 'onboard' as const,
    title: 'Finalize & Onboard',
    description: 'Once accepted, move the candidate into your employee directory and start onboarding.',
    action: 'Transition the record to New Hires in the Onboarding Center.',
  },
];

// ─── Range Negotiation Flowchart ─────────────────────────────────────────────

type RangeFlowStep = { id: number; label: string; sublabel: string; branch?: boolean };

const RANGE_FLOW_STEPS: RangeFlowStep[] = [
  { id: 1, label: 'Set Range',       sublabel: 'Employer sets min/max salary band' },
  { id: 2, label: 'Send Link',       sublabel: 'Magic link emailed to candidate' },
  { id: 3, label: 'Candidate Submits', sublabel: 'Candidate enters their private range' },
  { id: 4, label: 'Auto-Match',      sublabel: 'System checks for overlap', branch: true },
  { id: 5, label: 'Resolution',      sublabel: 'Accepted at midpoint — or re-negotiate' },
];

function RangeNegotiationFlowchart() {
  const [collapsed, setCollapsed] = useState(true);
  return (
    <div className="bg-zinc-900 rounded-2xl mb-6">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.03] transition-colors rounded-2xl"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Blind Range Negotiation</span>
          <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-amber-400/10 border border-amber-400/20 text-amber-400">How It Works</span>
        </div>
        <ChevronDown size={14} className={`text-zinc-600 transition-transform duration-200 shrink-0 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-zinc-800 px-5 pt-5 pb-5">
          {/* Flow steps */}
          <div className="relative overflow-x-auto no-scrollbar">
            <div className="flex items-start gap-0 min-w-max mb-5">
              {RANGE_FLOW_STEPS.map((step, idx) => (
                <div key={step.id} className="flex items-start">
                  <div className="flex flex-col items-center w-32">
                    <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-[10px] font-bold ${
                      step.branch ? 'border-amber-400/50 bg-amber-400/10 text-amber-400' : 'border-zinc-600 bg-zinc-800 text-zinc-400'
                    }`}>{step.id}</div>
                    <div className="mt-2 text-center text-[10px] font-bold uppercase tracking-wider text-zinc-300 leading-tight px-1">{step.label}</div>
                    <div className="mt-1 text-center text-[9px] text-zinc-500 leading-tight px-1">{step.sublabel}</div>
                  </div>
                  {idx < RANGE_FLOW_STEPS.length - 1 && (
                    <div className="w-8 h-0.5 mt-4 flex-shrink-0 bg-zinc-700" />
                  )}
                </div>
              ))}
            </div>
          </div>
          {/* Branch explanation */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[10px]">
            <div className="bg-matcha-500/10 border border-matcha-500/20 p-3 rounded-xl">
              <div className="font-bold uppercase tracking-wider text-matcha-400 mb-1">✓ Overlap Found</div>
              <div className="text-zinc-400">Offer accepted automatically at the midpoint of the overlapping range. Both parties are notified.</div>
            </div>
            <div className="bg-amber-400/10 border border-amber-400/20 p-3 rounded-xl">
              <div className="font-bold uppercase tracking-wider text-amber-400 mb-1">↻ No Overlap</div>
              <div className="text-zinc-400">Direction is shared (too low / too high) but exact numbers stay private. Employer can revise and re-send up to the round limit.</div>
            </div>
          </div>
          <p className="mt-3 text-[9px] text-zinc-500 leading-relaxed">
            Neither party sees the other's exact numbers until after a match. The system only reveals the direction of a miss, preserving negotiating privacy on both sides.
          </p>
        </div>
      )}
    </div>
  );
}


export function OfferLetters() {
  const { hasFeature } = useAuth();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const offerLettersPlusEnabled = hasFeature('offer_letters_plus');
  const [salaryType, setSalaryType] = useState<'fixed' | 'range'>('fixed');

  const { offerLetters, setOfferLetters, selectedLetter, setSelectedLetter, isLoading, reload } = useOfferLetters();

  const formHook = useOfferForm((letter) => {
    reload();
    setSelectedLetter(letter);
  });

  const guidanceHook = useOfferGuidance();

  const rangeHook = useRangeNegotiation(offerLetters, setOfferLetters, selectedLetter, setSelectedLetter);
  const { createMode, setCreateMode } = formHook;

  // Alias hook methods for easier template usage
  const { handleCreate, resetCreation, handleEditDraft, handleLogoChange, removeLogo } = formHook;
  const { handleGuidanceCityChange, handleGenerateGuidance } = guidanceHook;
  const { handleSendRange, handleReNegotiate } = rangeHook;

  const handleDownloadPdf = async (letter: OfferLetter) => {
    try {
      await offerLettersApi.downloadPdf(letter.id, letter.candidate_name);
    } catch (error) {
      console.error('Failed to download PDF:', error);
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

  const statusColors: Record<string, string> = isLight
    ? { draft: 'text-stone-500', sent: 'text-blue-700', accepted: 'text-matcha-700', rejected: 'text-red-700', expired: 'text-stone-400' }
    : { draft: 'text-zinc-500', sent: 'text-blue-400', accepted: 'text-matcha-400', rejected: 'text-red-400', expired: 'text-zinc-600' };

  const statusDotColors: Record<string, string> = isLight
    ? { draft: 'bg-stone-400', sent: 'bg-blue-500', accepted: 'bg-matcha-500', rejected: 'bg-red-500', expired: 'bg-stone-300' }
    : { draft: 'bg-zinc-600', sent: 'bg-blue-500', accepted: 'bg-matcha-500', rejected: 'bg-red-500', expired: 'bg-zinc-700' };

  // Wizard Steps Components
  const renderWizardStep = () => {
    switch (formHook.wizardStep) {
      case 1: // Basics
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Who are we hiring?</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Candidate Name</label>
                <input
                  type="text"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                  placeholder="Enter full name"
                  value={formHook.formData.candidate_name}
                  onChange={(e) => formHook.setFormData({...formHook.formData, candidate_name: e.target.value})}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Role Title</label>
                <input
                  type="text"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                  placeholder="e.g. Senior Engineer"
                  value={formHook.formData.position_title}
                  onChange={(e) => formHook.setFormData({...formHook.formData, position_title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Start Date</label>
                <input
                  type="date"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                  value={formHook.formData.start_date ? new Date(formHook.formData.start_date).toISOString().split('T')[0] : ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, start_date: e.target.value})}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Company Logo (optional)</label>
                <input type="file" ref={formHook.logoInputRef} accept="image/*" onChange={handleLogoChange} className="hidden" />
                {formHook.logoPreview ? (
                  <div className={`flex items-center gap-4 p-3 ${t.innerEl}`}>
                    <img src={formHook.logoPreview} alt="Logo preview" className="h-10 max-w-[120px] object-contain" />
                    <button type="button" onClick={removeLogo} className="text-xs text-red-500 hover:text-red-400 flex items-center gap-1">
                      <X size={14} /> Remove
                    </button>
                  </div>
                ) : (
                  <button type="button" onClick={() => formHook.logoInputRef.current?.click()} className={`w-full flex items-center justify-center gap-2 px-4 py-3 border border-dashed ${t.border} text-sm ${t.textMuted} transition-colors rounded-xl`}>
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
            <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Compensation Package</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <div className="flex gap-2 mb-2" data-tour="offer-range-toggle">
                  <button
                    type="button"
                    onClick={() => setSalaryType('fixed')}
                    className={`px-3 py-1 text-[10px] uppercase tracking-wider font-bold border rounded-lg ${salaryType === 'fixed' ? t.btnSecondaryActive : t.btnSecondary}`}
                  >
                    Fixed Amount
                  </button>
                  <button
                    type="button"
                    onClick={() => setSalaryType('range')}
                    className={`px-3 py-1 text-[10px] uppercase tracking-wider font-bold border rounded-lg ${salaryType === 'range' ? t.btnSecondaryActive : t.btnSecondary}`}
                  >
                    Salary Range
                  </button>
                </div>
              </div>
              {salaryType === 'fixed' ? (
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Annual Salary</label>
                <input
                  type="text"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                  placeholder="e.g. $150,000"
                  value={formHook.formData.salary || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, salary: e.target.value})}
                  autoFocus
                />
              </div>
              ) : (
              <div className="sm:col-span-2 flex gap-4" data-tour="offer-range-inputs">
                <div className="flex-1">
                  <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Min ($)</label>
                  <input
                    type="number"
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    placeholder="e.g. 140000"
                    value={formHook.formData.salary_range_min ?? ''}
                    onChange={(e) => formHook.setFormData({...formHook.formData, salary_range_min: e.target.value ? parseFloat(e.target.value) : undefined})}
                    autoFocus
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Max ($)</label>
                  <input
                    type="number"
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    placeholder="e.g. 160000"
                    value={formHook.formData.salary_range_max ?? ''}
                    onChange={(e) => formHook.setFormData({...formHook.formData, salary_range_max: e.target.value ? parseFloat(e.target.value) : undefined})}
                  />
                </div>
              </div>
              )}
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Bonus Potential</label>
                <input
                  type="text"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                  placeholder="e.g. 15% Annual"
                  value={formHook.formData.bonus || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, bonus: e.target.value})}
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Equity / Options</label>
                <input 
                  type="text" 
                  className={`w-full px-3 py-2 ${t.inputCls}`} 
                  placeholder="e.g. 5,000 RSUs"
                  value={formHook.formData.stock_options || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, stock_options: e.target.value})}
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Employment Type</label>
                <select
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    value={formHook.formData.employment_type || 'Full-Time Exempt'}
                    onChange={(e) => formHook.setFormData({...formHook.formData, employment_type: e.target.value})}
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
            <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Reporting & Location</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Manager Name</label>
                <input 
                  type="text" 
                  className={`w-full px-3 py-2 ${t.inputCls}`} 
                  placeholder="e.g. David Chen"
                  value={formHook.formData.manager_name || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, manager_name: e.target.value})}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Manager Title</label>
                <input 
                  type="text" 
                  className={`w-full px-3 py-2 ${t.inputCls}`} 
                  placeholder="e.g. VP of Engineering"
                  value={formHook.formData.manager_title || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, manager_title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Location</label>
                <input 
                  type="text" 
                  className={`w-full px-3 py-2 ${t.inputCls}`} 
                  placeholder="e.g. San Francisco, CA (Hybrid)"
                  value={formHook.formData.location || ''}
                  onChange={(e) => formHook.setFormData({...formHook.formData, location: e.target.value})}
                />
              </div>
            </div>
          </div>
        );
      case 4: // Benefits & Contingencies
        return (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <div>
              <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Benefits Package</h3>
              <div className="space-y-3">
                {/* Medical */}
                <div className={`p-3 ${t.innerEl}`}>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_medical || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textMain}">Medical insurance offered</span>
                  </label>
                  {formHook.formData.benefits_medical && (
                    <div className="mt-3 pl-0 sm:pl-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Employer Coverage %</label>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          placeholder="e.g. 80"
                          className={`w-full px-2 py-1.5 ${t.inputCls}`}
                          value={formHook.formData.benefits_medical_coverage || ''}
                          onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical_coverage: e.target.value ? parseInt(e.target.value) : undefined})}
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Waiting Period</label>
                        <select
                          className={`w-full px-2 py-1.5 ${t.inputCls}`}
                          value={formHook.formData.benefits_medical_waiting_days || 0}
                          onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical_waiting_days: parseInt(e.target.value)})}
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
                <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_dental || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_dental: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textDim}">Dental insurance</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_vision || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_vision: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textDim}">Vision insurance</span>
                  </label>
                </div>

                {/* 401k */}
                <div className={`p-3 ${t.innerEl}`}>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_401k || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_401k: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textMain}">401(k) retirement plan</span>
                  </label>
                  {formHook.formData.benefits_401k && (
                    <div className="mt-3 pl-6">
                      <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Employer Match (optional)</label>
                      <input
                        type="text"
                        placeholder="e.g. 4% match up to 6%"
                        className={`w-full px-2 py-1.5 ${t.inputCls}`}
                        value={formHook.formData.benefits_401k_match || ''}
                        onChange={(e) => formHook.setFormData({...formHook.formData, benefits_401k_match: e.target.value})}
                      />
                    </div>
                  )}
                </div>

                {/* Wellness */}
                <div>
                  <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Wellness Benefits (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. gym membership, mental health stipend"
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    value={formHook.formData.benefits_wellness || ''}
                    onChange={(e) => formHook.setFormData({...formHook.formData, benefits_wellness: e.target.value})}
                  />
                </div>

                {/* PTO */}
                <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_pto_vacation || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_pto_vacation: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textDim}">Paid vacation</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_pto_sick || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_pto_sick: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textDim}">Paid sick leave</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formHook.formData.benefits_holidays || false}
                      onChange={(e) => formHook.setFormData({...formHook.formData, benefits_holidays: e.target.checked})}
                      className={t.checkboxCls}
                    />
                    <span className="text-sm ${t.textDim}">Paid holidays</span>
                  </label>
                </div>

                {/* Other */}
                <div>
                  <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Other Benefits (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. parking, commuter benefits"
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    value={formHook.formData.benefits_other || ''}
                    onChange={(e) => formHook.setFormData({...formHook.formData, benefits_other: e.target.value})}
                  />
                </div>
              </div>
            </div>

            {/* Contingencies */}
            <div>
              <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-2`}>Offer Contingencies</h3>
              <p className={`text-xs ${t.textMuted} mb-3`}>I-9 employment verification is always required</p>
              <div className="flex gap-4 flex-wrap">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formHook.formData.contingency_background_check || false}
                    onChange={(e) => formHook.setFormData({...formHook.formData, contingency_background_check: e.target.checked})}
                    className={t.checkboxCls}
                  />
                  <span className="text-sm ${t.textDim}">Background check</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formHook.formData.contingency_credit_check || false}
                    onChange={(e) => formHook.setFormData({...formHook.formData, contingency_credit_check: e.target.checked})}
                    className={t.checkboxCls}
                  />
                  <span className="text-sm ${t.textDim}">Credit check</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formHook.formData.contingency_drug_screening || false}
                    onChange={(e) => formHook.setFormData({...formHook.formData, contingency_drug_screening: e.target.checked})}
                    className={t.checkboxCls}
                  />
                  <span className="text-sm ${t.textDim}">Drug screening</span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Offer Expiration Date</label>
              <input
                type="date"
                className={`w-full px-3 py-2 ${t.inputCls}`}
                value={formHook.formData.expiration_date ? new Date(formHook.formData.expiration_date).toISOString().split('T')[0] : ''}
                onChange={(e) => formHook.setFormData({...formHook.formData, expiration_date: e.target.value})}
              />
            </div>
          </div>
        );
      case 5: // Review
        return (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Review Offer</h3>
            <div className={t.reviewBlock}>
              <div className={`flex flex-col gap-1 ${t.reviewDivide} sm:flex-row sm:items-center sm:justify-between`}>
                <span className={t.textMuted}>Candidate</span>
                <span className={`font-medium ${t.textMain} sm:text-right`}>{formHook.formData.candidate_name}</span>
              </div>
              <div className={`flex flex-col gap-1 ${t.reviewDivide} sm:flex-row sm:items-center sm:justify-between`}>
                <span className={t.textMuted}>Role</span>
                <span className={`font-medium ${t.textMain} sm:text-right`}>{formHook.formData.position_title}</span>
              </div>
              <div className={`flex flex-col gap-1 ${t.reviewDivide} sm:flex-row sm:items-center sm:justify-between`}>
                <span className={t.textMuted}>Salary</span>
                <span className={`font-medium ${t.textMain} sm:text-right`}>{formHook.formData.salary}</span>
              </div>
              <div className={`flex flex-col gap-1 ${t.reviewDivide} sm:flex-row sm:items-center sm:justify-between`}>
                <span className={t.textMuted}>Start Date</span>
                <span className={`font-medium ${t.textMain} sm:text-right`}>{formHook.formData.start_date ? new Date(formHook.formData.start_date).toLocaleDateString() : 'TBD'}</span>
              </div>
              <div className="pt-2">
                <p className={`${t.textMuted} mb-1 text-xs uppercase tracking-wide`}>Benefits</p>
                <p className={t.textDim}>{formHook.formData.benefits || 'Standard benefits'}</p>
              </div>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-6 sm:px-8 lg:px-10 py-10 min-h-screen ${t.pageBg}`}>
      <div className="max-w-5xl mx-auto space-y-10">
        {/* Header */}
      <div className={`flex flex-col gap-4 mb-8 border-b ${t.border} pb-6 sm:flex-row sm:items-start sm:justify-between sm:mb-12 sm:pb-8`}>
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-2xl sm:text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>Offer Letters</h1>
            <FeatureGuideTrigger guideId="offer-letters" />
            <FeatureGuideTrigger guideId="offer-letters-range" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>Manage & Generate Candidate Offers</p>
        </div>
        <div className="relative w-full sm:w-auto">
          <button
            data-tour="offer-create-btn"
            onClick={() => setCreateMode(createMode ? null : 'select')} // Toggle selection mode
            className={`w-full sm:w-auto px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider transition-colors rounded-xl`}
          >
            Create Offer
          </button>
          
          {/* Mode Selection Dropdown */}
          {createMode === 'select' && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setCreateMode(null)} />
              <div data-tour="offer-create-mode" className={`absolute left-0 right-0 top-full mt-2 sm:left-auto sm:right-0 sm:w-48 ${t.dropdownBg} z-20 overflow-hidden animate-in fade-in zoom-in-95 duration-200 rounded-xl`}>
                <button 
                  onClick={() => setCreateMode('form')}
                  className={`w-full text-left px-4 py-3 ${t.dropdownItem} transition-colors border-b ${t.border}`}
                >
                  <span className={`block text-xs font-bold ${t.textMain} uppercase tracking-wide`}>Quick Form</span>
                  <span className={`block text-[10px] ${t.textMuted} mt-0.5`}>All fields in one view</span>
                </button>
                <button 
                  onClick={() => setCreateMode('wizard')}
                  className={`w-full text-left px-4 py-3 ${t.dropdownItem} transition-colors`}
                >
                  <span className={`block text-xs font-bold ${t.textMain} uppercase tracking-wide`}>Wizard Mode</span>
                  <span className={`block text-[10px] ${t.textMuted} mt-0.5`}>Step-by-step guidance</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <LifecycleWizard
        steps={OFFER_CYCLE_STEPS}
        activeStep={
          offerLetters.some(l => l.status === 'accepted') ? 5
          : offerLetters.some(l => l.status === 'sent') ? 4
          : offerLetters.length > 0 ? 3
          : 1
        }
        storageKey="offer-wizard-collapsed-v1"
        title="Offer Lifecycle"
      />
      <RangeNegotiationFlowchart />

      {offerLettersPlusEnabled && (
        <section className="mb-8 bg-zinc-900 rounded-2xl">
          <div className="border-b border-zinc-800 px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xs font-bold text-zinc-50 uppercase tracking-widest">Offer Guidance Plus</h2>
              <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-matcha-500/10 text-matcha-400 border border-matcha-500/20">
                Plus Feature
              </span>
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">
              Generate compensation guidance by role, city, and experience before drafting the offer.
            </p>
          </div>

          <form className="px-4 py-4 sm:px-5 sm:py-5" onSubmit={handleGenerateGuidance}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-5">
              <div className="lg:col-span-2">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Role Title</label>
                <input
                  type="text"
                  value={guidanceHook.guidanceRoleTitle}
                  onChange={(e) => guidanceHook.setGuidanceRoleTitle(e.target.value)}
                  placeholder="e.g. Senior Product Manager"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-zinc-600 placeholder:text-zinc-600 transition-colors"
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">City</label>
                <select
                  value={guidanceHook.guidanceCity}
                  onChange={(e) => handleGuidanceCityChange(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-zinc-600 transition-colors"
                >
                  {OFFER_GUIDANCE_CITY_OPTIONS.map((city) => (
                    <option key={city} value={city}>{city}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">State</label>
                <input
                  type="text"
                  value={guidanceHook.guidanceState}
                  onChange={(e) => guidanceHook.setGuidanceState(e.target.value)}
                  maxLength={3}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-zinc-600 transition-colors"
                />
              </div>
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Experience (Years)</label>
                <input
                  type="number"
                  min={0}
                  max={40}
                  value={guidanceHook.guidanceYearsExperience}
                  onChange={(e) => guidanceHook.setGuidanceYearsExperience(Math.max(0, Math.min(40, Number(e.target.value) || 0)))}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-zinc-600 transition-colors"
                />
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="w-full sm:w-64">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Employment Type</label>
                <select
                  value={guidanceHook.guidanceEmploymentType}
                  onChange={(e) => guidanceHook.setGuidanceEmploymentType(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-zinc-600 transition-colors"
                >
                  {EMPLOYMENT_TYPES.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={guidanceHook.guidanceLoading}
                className="inline-flex items-center justify-center px-5 py-2 bg-zinc-50 text-zinc-900 hover:bg-white text-xs font-bold uppercase tracking-wider disabled:opacity-60 disabled:cursor-not-allowed transition-colors rounded-xl"
              >
                {guidanceHook.guidanceLoading ? 'Generating...' : 'Generate Guidance'}
              </button>
            </div>

            {guidanceHook.guidanceError && (
              <p className="mt-3 text-xs text-red-400">{guidanceHook.guidanceError}</p>
            )}

            {guidanceHook.guidanceResult && (
              <div className="mt-5 bg-zinc-800 border border-zinc-700 p-4 rounded-xl">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Base Salary Range</p>
                    <p className="mt-1 text-sm font-bold text-zinc-50">
                      {formatUsd(guidanceHook.guidanceResult.salary_low)} - {formatUsd(guidanceHook.guidanceResult.salary_high)}
                    </p>
                    <p className="text-[11px] text-zinc-500">Midpoint: {formatUsd(guidanceHook.guidanceResult.salary_mid)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Bonus Target</p>
                    <p className="mt-1 text-sm font-bold text-zinc-50">
                      {guidanceHook.guidanceResult.bonus_target_pct_low}% - {guidanceHook.guidanceResult.bonus_target_pct_high}%
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Role Family</p>
                    <p className="mt-1 text-sm font-bold text-zinc-50 capitalize">
                      {guidanceHook.guidanceResult.role_family.replace(/_/g, ' ')}
                    </p>
                    <p className="text-[11px] text-zinc-500">
                      {guidanceHook.guidanceResult.normalized_city}
                      {guidanceHook.guidanceResult.normalized_state ? `, ${guidanceHook.guidanceResult.normalized_state}` : ''}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500">Confidence</p>
                    <p className="mt-1 text-sm font-bold text-zinc-50">{Math.round(guidanceHook.guidanceResult.confidence * 100)}%</p>
                    <div className="mt-2 h-1.5 w-full bg-zinc-700 rounded-full">
                      <div
                        className="h-full bg-matcha-500 transition-all rounded-full"
                        style={{ width: `${Math.round(guidanceHook.guidanceResult.confidence * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
                <div className="mt-4">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Equity Guidance</p>
                  <p className="mt-1 text-xs text-zinc-300">{guidanceHook.guidanceResult.equity_guidance}</p>
                </div>
                <div className="mt-4">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Rationale</p>
                  <ul className="space-y-1.5 text-xs text-zinc-400">
                    {guidanceHook.guidanceResult.rationale.map((line) => (
                      <li key={line}>• {line}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </form>
        </section>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
           <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading...</div>
        </div>
      ) : offerLetters.length === 0 ? (
        <div className={`text-center py-24 ${t.emptyBorder}`}>
          <div className={`text-xs ${t.textMuted} mb-4 font-mono uppercase tracking-wider`}>NO OFFERS GENERATED</div>
          <button
            data-tour="offer-first-create-btn"
            onClick={() => setCreateMode('wizard')}
            className={`text-xs ${t.textMain} font-bold uppercase tracking-wider underline underline-offset-4`}
          >
            Create your first offer
          </button>
        </div>
      ) : (
        <div data-tour="offer-list">
          <div className="md:hidden space-y-3">
            {offerLetters.map((letter) => (
              <button
                key={letter.id}
                type="button"
                className={`w-full text-left ${t.card} p-4 ${t.rowHover} transition-colors`}
                onClick={() => setSelectedLetter(letter)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className={`text-sm font-bold ${t.textMain} truncate`}>{letter.candidate_name}</h3>
                    <p className={`text-[10px] ${t.textMuted} mt-0.5 truncate`}>{letter.company_name}</p>
                  </div>
                  <span className={`shrink-0 text-[10px] font-bold ${statusColors[letter.status] || t.textMuted} uppercase tracking-wider`}>
                    {letter.status}
                  </span>
                </div>
                {letter.range_match_status && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className={`text-[10px] px-2 py-0.5 font-bold uppercase tracking-wider ${
                      letter.range_match_status === 'matched' ? 'bg-matcha-500/10 text-matcha-500 border border-matcha-500/20' :
                      letter.range_match_status === 'pending_candidate' ? 'bg-amber-400/10 text-amber-500 border border-amber-400/30' :
                      'bg-red-400/10 text-red-500 border border-red-400/30'
                    }`}>
                      {letter.range_match_status === 'matched' && letter.matched_salary
                        ? `Matched at ${formatUsd(letter.matched_salary)}`
                        : letter.range_match_status === 'pending_candidate'
                        ? 'Awaiting candidate'
                        : letter.range_match_status === 'no_match_low'
                        ? 'No match - offer too low'
                        : 'No match - offer too high'}
                    </span>
                    {letter.negotiation_round != null && letter.negotiation_round > 0 && (
                      <span className="text-[10px] text-zinc-600">
                        Round {letter.negotiation_round} of {letter.max_negotiation_rounds}
                      </span>
                    )}
                  </div>
                )}
                <div className="mt-3 flex items-center justify-between gap-3">
                  <p className={`text-xs ${t.textDim} truncate`}>{letter.position_title}</p>
                  <span className={`text-[10px] ${t.textMuted} font-mono shrink-0`}>
                    {new Date(letter.created_at).toLocaleDateString()}
                  </span>
                </div>
              </button>
            ))}
          </div>

          <div className={`hidden md:block ${t.card} overflow-hidden`}>
             {/* List Header */}
             <div className={`flex items-center gap-4 py-3 px-4 text-[10px] ${t.textMuted} uppercase tracking-widest ${t.tableHeader} border-b ${t.border}`}>
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
                className={`group flex items-center gap-4 py-4 px-4 cursor-pointer ${t.rowHover} transition-colors`}
                onClick={() => setSelectedLetter(letter)}
              >
                <div className="w-8 flex justify-center">
                   <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[letter.status] || 'bg-zinc-700'}`} />
                </div>
                
                <div className="flex-1">
                   <h3 className={`text-sm font-bold ${t.textMain}`}>
                     {letter.candidate_name}
                   </h3>
                   <p className={`text-[10px] ${t.textMuted} mt-0.5`}>{letter.company_name}</p>
                </div>

                <div className={`w-48 text-xs ${t.textDim}`}>
                   {letter.position_title}
                </div>

                <div className="w-32 flex flex-col gap-1">
                   <span className={`text-[10px] font-bold ${statusColors[letter.status] || t.textMuted} uppercase tracking-wider`}>
                     {letter.status}
                   </span>
                   {letter.range_match_status && (
                     <span className={`text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-wider inline-block w-fit ${
                       letter.range_match_status === 'matched' ? 'bg-matcha-500/10 text-matcha-500' :
                       letter.range_match_status === 'pending_candidate' ? 'bg-amber-400/10 text-amber-500' :
                       'bg-red-400/10 text-red-500'
                     }`}>
                       {letter.range_match_status === 'matched' ? 'Matched' :
                        letter.range_match_status === 'pending_candidate' ? 'Awaiting' :
                        'No match'}
                     </span>
                   )}
                </div>

                <div className={`w-32 text-right text-[10px] ${t.textMuted} font-mono`}>
                   {new Date(letter.created_at).toLocaleDateString()}
                </div>
                
                <div className={`w-8 flex justify-center ${t.chevron}`}>
                   <ChevronRight className="w-4 h-4" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Create Modal (Form or Wizard) */}
      {(createMode === 'form' || createMode === 'wizard') && (
         <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/80 backdrop-blur-sm p-2 sm:p-4">
            <div className={`w-full max-w-3xl h-[calc(100vh-1rem)] sm:h-auto sm:max-h-[90vh] ${t.modalBg} flex flex-col`}>
               <div className={`flex items-start justify-between gap-3 p-4 ${t.modalHeader} sm:items-center sm:p-6`}>
                  <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                    <h2 className={`text-base sm:text-xl font-bold ${t.textMain} uppercase tracking-tight`}>
                      {createMode === 'wizard' ? `Step ${formHook.wizardStep} of 5` : 'Create Offer Letter'}
                    </h2>
                    {createMode === 'wizard' && (
                      <div className="flex gap-1 sm:ml-4">
                        {[1, 2, 3, 4, 5].map(step => (
                          <div 
                            key={step} 
                            className={`w-1.5 h-1.5 rounded-full ${step <= formHook.wizardStep ? t.wizardActive : t.wizardInactive}`}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <button onClick={resetCreation} className={t.closeBtnCls}>
                     <X size={20} />
                  </button>
               </div>
               
               <div className="flex-1 overflow-y-auto p-4 sm:p-8">
                {createMode === 'wizard' ? (
                  renderWizardStep()
                ) : (
                  <form className="space-y-6 sm:space-y-8" id="quick-form" onSubmit={handleCreate}>
                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Candidate & Role</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Candidate Name</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="Enter full name"
                              value={formHook.formData.candidate_name}
                              onChange={(e) => formHook.setFormData({...formHook.formData, candidate_name: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Role Title</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. Senior Engineer"
                              value={formHook.formData.position_title}
                              onChange={(e) => formHook.setFormData({...formHook.formData, position_title: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Start Date</label>
                            <input 
                              type="date" 
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              value={formHook.formData.start_date ? new Date(formHook.formData.start_date).toISOString().split('T')[0] : ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, start_date: e.target.value})}
                              required
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Expiration Date</label>
                            <input 
                              type="date" 
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              value={formHook.formData.expiration_date ? new Date(formHook.formData.expiration_date).toISOString().split('T')[0] : ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, expiration_date: e.target.value})}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Compensation</h3>
                        <div className="flex gap-2 mb-2">
                          <button
                            type="button"
                            onClick={() => setSalaryType('fixed')}
                            className={`px-3 py-1 text-[10px] uppercase tracking-wider font-bold border rounded-lg ${salaryType === 'fixed' ? t.btnSecondaryActive : t.btnSecondary}`}
                          >
                            Fixed Amount
                          </button>
                          <button
                            type="button"
                            onClick={() => setSalaryType('range')}
                            className={`px-3 py-1 text-[10px] uppercase tracking-wider font-bold border rounded-lg ${salaryType === 'range' ? t.btnSecondaryActive : t.btnSecondary}`}
                          >
                            Salary Range
                          </button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {salaryType === 'fixed' ? (
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Annual Salary</label>
                            <input
                              type="text"
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              placeholder="e.g. $150,000"
                              value={formHook.formData.salary || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, salary: e.target.value})}
                            />
                          </div>
                          ) : (
                          <div className="md:col-span-2 flex gap-4">
                            <div className="flex-1">
                              <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Min ($)</label>
                              <input
                                type="number"
                                className={`w-full px-3 py-2 ${t.inputCls}`}
                                placeholder="e.g. 140000"
                                value={formHook.formData.salary_range_min ?? ''}
                                onChange={(e) => formHook.setFormData({...formHook.formData, salary_range_min: e.target.value ? parseFloat(e.target.value) : undefined})}
                              />
                            </div>
                            <div className="flex-1">
                              <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Max ($)</label>
                              <input
                                type="number"
                                className={`w-full px-3 py-2 ${t.inputCls}`}
                                placeholder="e.g. 160000"
                                value={formHook.formData.salary_range_max ?? ''}
                                onChange={(e) => formHook.setFormData({...formHook.formData, salary_range_max: e.target.value ? parseFloat(e.target.value) : undefined})}
                              />
                            </div>
                          </div>
                          )}
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Bonus Potential</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. 15% Annual"
                              value={formHook.formData.bonus || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, bonus: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Equity / Options</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. 5,000 RSUs"
                              value={formHook.formData.stock_options || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, stock_options: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Employment Type</label>
                            <select
                                className={`w-full px-3 py-2 ${t.inputCls}`}
                                value={formHook.formData.employment_type || 'Full-Time Exempt'}
                                onChange={(e) => formHook.setFormData({...formHook.formData, employment_type: e.target.value})}
                            >
                                {EMPLOYMENT_TYPES.map(type => (
                                  <option key={type} value={type}>{type}</option>
                                ))}
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Reporting & Location</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Manager Name</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. David Chen"
                              value={formHook.formData.manager_name || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, manager_name: e.target.value})}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Manager Title</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. VP of Engineering"
                              value={formHook.formData.manager_title || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, manager_title: e.target.value})}
                            />
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-[10px] tracking-wider uppercase ${t.textMuted} mb-1.5">Location</label>
                            <input 
                              type="text" 
                              className={`w-full px-3 py-2 ${t.inputCls}`} 
                              placeholder="e.g. San Francisco, CA (Hybrid)"
                              value={formHook.formData.location || ''}
                              onChange={(e) => formHook.setFormData({...formHook.formData, location: e.target.value})}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Benefits Package</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_medical || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Medical insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_dental || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_dental: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Dental insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_vision || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_vision: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Vision insurance</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_401k || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_401k: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">401(k)</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_pto_vacation || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_pto_vacation: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Paid vacation</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_pto_sick || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_pto_sick: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Paid sick leave</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.benefits_holidays || false} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_holidays: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Paid holidays</span>
                          </label>
                        </div>
                        {formHook.formData.benefits_medical && (
                          <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 pl-0 sm:pl-4 border-l-2 ${t.border}`}>
                            <div>
                              <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Medical Coverage %</label>
                              <input type="number" min="0" max="100" placeholder="e.g. 80" className={`w-full px-2 py-1.5 ${t.inputCls}`} value={formHook.formData.benefits_medical_coverage || ''} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical_coverage: e.target.value ? parseInt(e.target.value) : undefined})} />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Waiting Period</label>
                              <select className={`w-full px-2 py-1.5 ${t.inputCls}`} value={formHook.formData.benefits_medical_waiting_days || 0} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_medical_waiting_days: parseInt(e.target.value)})}>
                                <option value={0}>No waiting</option>
                                <option value={30}>30 days</option>
                                <option value={60}>60 days</option>
                                <option value={90}>90 days</option>
                              </select>
                            </div>
                          </div>
                        )}
                        {formHook.formData.benefits_401k && (
                          <div className={`pl-4 border-l-2 ${t.border}`}>
                            <label className="block text-[10px] uppercase ${t.textMuted} mb-1">401(k) Match</label>
                            <input type="text" placeholder="e.g. 4% match" className={`w-full px-2 py-1.5 ${t.inputCls}`} value={formHook.formData.benefits_401k_match || ''} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_401k_match: e.target.value})} />
                          </div>
                        )}
                        <div>
                          <label className="block text-[10px] uppercase ${t.textMuted} mb-1">Other Benefits</label>
                          <input type="text" placeholder="e.g. wellness stipend, parking" className={`w-full px-3 py-2 ${t.inputCls}`} value={formHook.formData.benefits_other || ''} onChange={(e) => formHook.setFormData({...formHook.formData, benefits_other: e.target.value})} />
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Contingencies</h3>
                        <p className={`text-xs ${t.textMuted}`}>I-9 verification is always required</p>
                        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-6">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.contingency_background_check || false} onChange={(e) => formHook.setFormData({...formHook.formData, contingency_background_check: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Background check</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.contingency_credit_check || false} onChange={(e) => formHook.setFormData({...formHook.formData, contingency_credit_check: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Credit check</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formHook.formData.contingency_drug_screening || false} onChange={(e) => formHook.setFormData({...formHook.formData, contingency_drug_screening: e.target.checked})} className={t.checkboxCls} />
                            <span className="text-sm ${t.textDim}">Drug screening</span>
                          </label>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <h3 className={`text-xs font-bold ${t.textMain} uppercase tracking-wider border-b ${t.border} pb-2`}>Company Logo</h3>
                        <div>
                          <input type="file" ref={formHook.logoInputRef} accept="image/*" onChange={handleLogoChange} className="hidden" />
                          {formHook.logoPreview ? (
                            <div className="flex flex-wrap items-center gap-4">
                              <img src={formHook.logoPreview} alt="Logo preview" className="h-12 max-w-[150px] object-contain" />
                              <button type="button" onClick={removeLogo} className="text-xs text-red-500 hover:text-red-400">Remove</button>
                            </div>
                          ) : (
                            <button type="button" onClick={() => formHook.logoInputRef.current?.click()} className={`w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2 border border-dashed ${t.border} text-sm ${t.textMuted} transition-colors rounded-xl`}>
                              <Upload size={16} />
                              Upload company logo
                            </button>
                          )}
                        </div>
                      </div>
                  </form>
                )}
               </div>

               <div className={`flex flex-col gap-3 p-4 ${t.modalFooter} sm:flex-row sm:items-center sm:justify-between sm:p-6`}>
                  <Button variant="secondary" type="button" onClick={resetCreation} className={`w-full sm:w-auto ${t.btnSecondary}`}>Cancel</Button>
                  
                  {createMode === 'wizard' ? (
                    <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row">
                      {formHook.wizardStep > 1 && (
                        <Button variant="secondary" onClick={() => formHook.setWizardStep(formHook.wizardStep - 1)} className={`w-full sm:w-auto ${t.btnSecondary}`}>
                          <ArrowLeft size={14} className="mr-2" /> Back
                        </Button>
                      )}
                      {formHook.wizardStep < 5 ? (
                        <Button onClick={() => formHook.setWizardStep(formHook.wizardStep + 1)} className={`w-full sm:w-auto ${t.btnPrimary} rounded-xl`}>
                          Next <ArrowRight size={14} className="ml-2" />
                        </Button>
                      ) : (
                        <Button onClick={() => handleCreate()} disabled={formHook.isSubmitting} className={`w-full sm:w-auto ${t.btnPrimary} rounded-xl`}>
                          {formHook.isSubmitting ? 'Generating...' : 'Generate Offer'} <Check size={14} className="ml-2" />
                        </Button>
                      )}
                    </div>
                  ) : (
                    <Button type="submit" form="quick-form" disabled={formHook.isSubmitting} className={`w-full sm:w-auto ${t.btnPrimary} rounded-xl`}>
                      {formHook.isSubmitting ? 'Generating...' : 'Generate Offer'}
                    </Button>
                  )}
               </div>
            </div>
         </div>
      )}

      {/* Detail Modal (Existing View Logic) */}
      {selectedLetter && (
        <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/80 backdrop-blur-sm p-2 sm:p-4 animate-in fade-in duration-200">
          <div className={`w-full max-w-4xl h-[calc(100vh-1rem)] sm:h-auto sm:max-h-[90vh] flex flex-col ${t.modalBg} overflow-hidden`}>
             {/* Modal Header */}
             <div className={`p-4 sm:p-6 ${t.modalHeader} flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between`}>
                <div>
                   <h2 className={`text-xl font-bold ${t.textMain} tracking-tight`}>Offer Details</h2>
                   <p className={`text-xs ${t.textMuted} mt-1 font-mono uppercase tracking-wide break-all`}>{selectedLetter.id}</p>
                </div>
                <div className="flex items-center gap-2 sm:gap-4">
                   <span className={`px-2 py-1 text-[10px] uppercase tracking-wider font-bold ${statusColors[selectedLetter.status]} ${t.statusBadgeBg} rounded-lg`}>
                      {selectedLetter.status}
                   </span>
                   <button
                    onClick={() => setSelectedLetter(null)}
                    className={`p-2 rounded-full transition-colors ${t.closeBtnCls}`}
                  >
                    <X size={20} />
                  </button>
                </div>
             </div>

             {/* Modal Content */}
             <div className="flex-1 overflow-y-auto p-4 sm:p-8">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:gap-8">
                   {/* Left Sidebar: Metadata */}
                   <div className="space-y-6">
                      <div>
                         <label className={`text-[10px] ${t.textMuted} uppercase tracking-widest block mb-1`}>Candidate</label>
                         <p className={`${t.textMain} font-bold`}>{selectedLetter.candidate_name}</p>
                      </div>
                      <div>
                         <label className={`text-[10px] ${t.textMuted} uppercase tracking-widest block mb-1`}>Position</label>
                         <p className={t.textDim}>{selectedLetter.position_title}</p>
                      </div>
                       <div>
                         <label className={`text-[10px] ${t.textMuted} uppercase tracking-widest block mb-1`}>Company</label>
                         <p className={t.textDim}>{selectedLetter.company_name}</p>
                      </div>
                      
                      {/* Range negotiation status */}
                      {selectedLetter.range_match_status && (
                        <div data-tour="offer-range-status">
                          <label className={`text-[10px] ${t.textMuted} uppercase tracking-widest block mb-1`}>Range Negotiation</label>
                          <span className={`text-xs px-2 py-1 font-bold uppercase tracking-wider inline-block ${
                            selectedLetter.range_match_status === 'matched' ? 'bg-matcha-500/10 text-matcha-500 border border-matcha-500/20' :
                            selectedLetter.range_match_status === 'pending_candidate' ? 'bg-amber-400/10 text-amber-500 border border-amber-400/30' :
                            'bg-red-400/10 text-red-500 border border-red-400/30'
                          }`}>
                            {selectedLetter.range_match_status === 'matched' && selectedLetter.matched_salary
                              ? `Matched at ${formatUsd(selectedLetter.matched_salary)}`
                              : selectedLetter.range_match_status === 'pending_candidate'
                              ? 'Awaiting candidate'
                              : selectedLetter.range_match_status === 'no_match_low'
                              ? 'No match - offer too low'
                              : 'No match - offer too high'}
                          </span>
                          {selectedLetter.negotiation_round != null && selectedLetter.negotiation_round > 0 && (
                            <p className="text-[10px] text-zinc-600 mt-1">
                              Round {selectedLetter.negotiation_round} of {selectedLetter.max_negotiation_rounds}
                            </p>
                          )}
                        </div>
                      )}

                      <div className={`pt-6 border-t ${t.border} space-y-3`}>
                         <Button variant="secondary" className={`w-full justify-center ${t.btnSecondary}`} onClick={() => handleDownloadPdf(selectedLetter)}>Download PDF</Button>
                         {selectedLetter.status === 'draft' && (
                           <Button variant="secondary" className={`w-full justify-center ${t.btnSecondary}`} onClick={() => handleEditDraft(selectedLetter)}>Edit Draft</Button>
                         )}
                         {selectedLetter.salary_range_min != null && selectedLetter.salary_range_max != null && !selectedLetter.range_match_status && (
                           <Button data-tour="offer-send-range-btn" variant="secondary" className="w-full justify-center bg-transparent border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 rounded-xl" onClick={() => { rangeHook.setShowSendRangePrompt(selectedLetter.id); rangeHook.setSendRangeEmail(selectedLetter.candidate_email || ''); }}>Send Range Offer</Button>
                         )}
                         {(selectedLetter.range_match_status === 'no_match_low' || selectedLetter.range_match_status === 'no_match_high') &&
                           (selectedLetter.negotiation_round ?? 1) < (selectedLetter.max_negotiation_rounds ?? 3) && (
                           <Button data-tour="offer-renegotiate-btn" variant="secondary" className="w-full justify-center bg-transparent border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 rounded-xl" onClick={() => handleReNegotiate(selectedLetter.id)}>Re-negotiate</Button>
                         )}
                      </div>
                   </div>

                   {/* Right Content: Preview */}
                   <div className="lg:col-span-2">
                      <div className="bg-white text-zinc-900 font-serif p-5 sm:p-12 shadow-sm min-h-[520px] sm:min-h-[600px] text-xs sm:text-[13px] leading-relaxed">
                         <div className="space-y-6 sm:space-y-8">
                            <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-start border-b border-zinc-100 pb-6">
                              <div>
                                {selectedLetter.company_logo_url && (
                                  <img src={selectedLetter.company_logo_url} alt="Company logo" className="h-10 max-w-[150px] object-contain mb-2" />
                                )}
                                <h3 className="font-bold text-lg tracking-tight mb-1">{selectedLetter.company_name}</h3>
                                <p className="text-zinc-500 font-sans text-[10px] uppercase tracking-widest">Official Offer of Employment</p>
                              </div>
                              <div className="sm:text-right">
                                  <p className="font-sans text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Date</p>
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
                              <div className="bg-zinc-50 p-4 sm:p-6 rounded border border-zinc-100 space-y-4 font-sans mt-6 mb-6">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-200 pb-2">Compensation & Terms</h4>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-6 gap-x-4">
                                  <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Annual Salary</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.salary || 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Start Date</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.start_date ? new Date(selectedLetter.start_date).toLocaleDateString() : 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Bonus Potential</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.bonus || 'N/A'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Equity / Options</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.stock_options || 'N/A'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Employment Type</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.employment_type || 'Full-Time Exempt'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-500 uppercase mb-1">Location</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.location || 'Remote'}</p>
                                  </div>
                                </div>
                              </div>

                              {/* Benefits Section */}
                              <div className="space-y-2">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-500 font-sans">Benefits</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  {generateBenefitsText(selectedLetter) || 'Standard company benefits package.'}
                                </p>
                              </div>

                              {/* Contingencies Section */}
                              <div className="space-y-2">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-500 font-sans">Contingencies</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  {generateContingenciesText(selectedLetter)}
                                </p>
                              </div>

                              {/* At-Will Employment */}
                              <div className="space-y-2 mt-6">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-500 font-sans">At-Will Employment</h4>
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
                            <div className="mt-12 sm:mt-16 pt-6 sm:pt-8 border-t border-zinc-100 flex flex-col gap-8 sm:flex-row sm:justify-between sm:items-end">
                              <div>
                                <div className="w-full sm:w-48 h-px bg-zinc-300 mb-2"></div>
                                <p className="font-bold text-zinc-900">{selectedLetter.manager_name || 'Hiring Manager'}</p>
                                <p className="font-sans text-[10px] text-zinc-500 uppercase tracking-widest">Authorized Signature</p>
                              </div>
                              <div className="sm:text-right">
                                  <p className="font-sans text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Candidate Acceptance</p>
                                  <div className="w-full sm:w-48 h-10 border-b border-dashed border-zinc-300 mb-1"></div>
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
      {/* Send Range Email Prompt */}
      {rangeHook.showSendRangePrompt && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className={`w-full max-w-sm ${t.modalBg} p-6`}>
            <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider mb-4`}>Send Range Offer</h3>
            <p className={`text-xs ${t.textMuted} mb-4`}>Enter the candidate's email to send the salary range negotiation link.</p>
            <input
              type="email"
              className={`w-full px-3 py-2 ${t.inputCls} mb-4`}
              placeholder="candidate@email.com"
              value={rangeHook.sendRangeEmail}
              onChange={(e) => rangeHook.setSendRangeEmail(e.target.value)}
              autoFocus
            />
            <div className="flex gap-3">
              <button
                onClick={() => { rangeHook.setShowSendRangePrompt(null); rangeHook.setSendRangeEmail(''); }}
                className={`flex-1 px-4 py-2 text-xs font-bold uppercase tracking-wider ${t.btnSecondary} transition-colors rounded-xl`}
              >
                Cancel
              </button>
              <button
                onClick={() => handleSendRange(rangeHook.showSendRangePrompt as string)}
                disabled={!rangeHook.sendRangeEmail || rangeHook.isSubmitting}
                className={`flex-1 px-4 py-2 text-xs font-bold uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50 transition-colors rounded-xl`}
              >
                {rangeHook.isSubmitting ? 'Sending...' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

export default OfferLetters;
