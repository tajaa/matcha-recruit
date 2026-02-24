import { useState, useRef } from 'react';
import { offerLetters as offerLettersApi } from '../../api/client';
import type { OfferLetterCreate, OfferLetter } from '../../types';

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
  contingency_background_check: false,
  contingency_credit_check: false,
  contingency_drug_screening: false,
  company_logo_url: '',
};

export function useOfferForm(onSuccess: (letter: OfferLetter) => void) {
  const [createMode, setCreateMode] = useState<'form' | 'wizard' | 'select' | null>(null);
  const [wizardStep, setWizardStep] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<OfferLetterCreate>(initialFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);

  const handleCreate = async (e?: React.FormEvent) => {
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
        const { url } = await offerLettersApi.uploadLogo(savedOffer.id, logoFile);
        setFormData((prev) => ({ ...prev, company_logo_url: url }));
      }

      onSuccess(savedOffer);
      resetCreation();
    } catch (error) {
      console.error('Failed to create/update offer letter:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

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
    setCreateMode('form');
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

  return {
    createMode,
    setCreateMode,
    wizardStep,
    setWizardStep,
    editingId,
    formData,
    setFormData,
    isSubmitting,
    logoFile,
    logoPreview,
    logoInputRef,
    handleCreate,
    resetCreation,
    handleEditDraft,
    handleLogoChange,
    removeLogo,
  };
}
