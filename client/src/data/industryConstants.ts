// Shared industry and healthcare specialty constants
// Values align with compliance_registry.py industry_tag sub-keys

export const INDUSTRY_OPTIONS = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'biotech', label: 'Biotech / Life Sciences' },
  { value: 'dental', label: 'Dental' },
  { value: 'technology', label: 'Technology' },
  { value: 'retail', label: 'Retail' },
  { value: 'hospitality', label: 'Hospitality' },
  { value: 'education', label: 'Education' },
  { value: 'legal', label: 'Legal' },
  { value: 'financial_services', label: 'Financial Services' },
  { value: 'construction', label: 'Construction' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'nonprofit', label: 'Non-Profit' },
  { value: 'real_estate', label: 'Real Estate' },
  { value: 'transportation', label: 'Transportation' },
  { value: 'other', label: 'Other' },
]

// Values MUST match compliance_registry.py industry_tag sub-keys
// (the part after "healthcare:" — e.g. "oncology", "pharmacy", etc.)
export const HEALTHCARE_SPECIALTIES = [
  { value: 'oncology', label: 'Oncology' },
  { value: 'primary_care', label: 'Primary Care' },
  { value: 'cardiology', label: 'Cardiology' },
  { value: 'pediatric', label: 'Pediatrics' },
  { value: 'pharmacy', label: 'Pharmacy' },
  { value: 'behavioral_health', label: 'Behavioral Health' },
  { value: 'telehealth', label: 'Telehealth' },
  { value: 'managed_care', label: 'Managed Care' },
  { value: 'devices', label: 'Medical Devices' },
  { value: 'transplant', label: 'Transplant & Organ' },
  { value: 'nonprofit', label: 'Nonprofit Healthcare' },
  { value: 'orthopedics', label: 'Orthopedics' },
  { value: 'neurology', label: 'Neurology' },
  { value: 'dermatology', label: 'Dermatology' },
  { value: 'emergency', label: 'Emergency Medicine' },
  { value: 'surgery', label: 'Surgery' },
]

export const SIZE_OPTIONS = [
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-500', label: '201-500 employees' },
  { value: '501-1000', label: '501-1,000 employees' },
  { value: '1001+', label: '1,000+ employees' },
]

// Industries that show the healthcare specialties sub-selector
export const HEALTHCARE_INDUSTRIES = new Set(['healthcare', 'biotech', 'dental'])
