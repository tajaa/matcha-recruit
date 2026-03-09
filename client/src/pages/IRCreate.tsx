import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, irIncidents } from '../api/client';
import { complianceAPI, type BusinessLocation } from '../api/compliance';
import type { IRIncidentType, IRSeverity, IRWitness, IRIncidentCreate } from '../types';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { useIsLightMode } from '../hooks/useIsLightMode';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  input: 'w-full px-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm placeholder-stone-400 focus:outline-none focus:border-stone-400 transition-colors rounded-xl',
  textarea: 'w-full px-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm placeholder-stone-400 focus:outline-none focus:border-stone-400 transition-colors rounded-xl resize-none',
  select: 'w-full px-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm focus:outline-none focus:border-stone-400 transition-colors rounded-xl cursor-pointer',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  chipActive: 'bg-zinc-900 text-zinc-50 rounded-xl',
  chipInactive: 'text-stone-500 hover:text-zinc-900 rounded-xl',
  sectionBorder: 'border-stone-200',
  sevDots: { critical: 'bg-zinc-900', high: 'bg-stone-600', medium: 'bg-stone-400', low: 'bg-stone-300' } as Record<string, string>,
  sevRing: 'ring-offset-stone-300',
  checkboxBg: 'bg-white border-stone-300',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  input: 'w-full px-3 py-2 bg-zinc-800 border border-white/10 text-zinc-100 text-sm placeholder-zinc-600 focus:outline-none focus:border-white/20 transition-colors rounded-xl',
  textarea: 'w-full px-3 py-2 bg-zinc-800 border border-white/10 text-zinc-100 text-sm placeholder-zinc-600 focus:outline-none focus:border-white/20 transition-colors rounded-xl resize-none',
  select: 'w-full px-3 py-2 bg-zinc-800 border border-white/10 text-zinc-100 text-sm focus:outline-none focus:border-white/20 transition-colors rounded-xl cursor-pointer',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  chipActive: 'bg-zinc-700 text-zinc-100 rounded-xl',
  chipInactive: 'text-zinc-500 hover:text-zinc-100 rounded-xl',
  sectionBorder: 'border-zinc-800',
  sevDots: { critical: 'bg-zinc-100', high: 'bg-zinc-400', medium: 'bg-zinc-500', low: 'bg-zinc-600' } as Record<string, string>,
  sevRing: 'ring-offset-zinc-950',
  checkboxBg: 'bg-zinc-800 border-zinc-700',
} as const;

const TYPES: { value: IRIncidentType; label: string }[] = [
  { value: 'safety', label: 'Safety' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'property', label: 'Property' },
  { value: 'near_miss', label: 'Near Miss' },
  { value: 'other', label: 'Other' },
];

const SEVERITIES: { value: IRSeverity; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Med' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Crit' },
];

const BODY_PARTS = ['Head', 'Neck', 'Back', 'Arm', 'Hand', 'Leg', 'Foot', 'Other'];
const INJURY_TYPES = ['Cut', 'Burn', 'Strain', 'Fracture', 'Contusion', 'Other'];
const TREATMENTS = ['None', 'First Aid', 'Medical', 'ER', 'Hospital'];

export function IRCreate() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const th = isLight ? LT : DK;
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [incidentType, setIncidentType] = useState<IRIncidentType>('safety');
  const [severity, setSeverity] = useState<IRSeverity>('medium');
  const [occurredAt, setOccurredAt] = useState('');
  const [location, setLocation] = useState('');
  const [reportedByName, setReportedByName] = useState('');
  const [reportedByEmail, setReportedByEmail] = useState('');
  const [witnesses, setWitnesses] = useState<IRWitness[]>([]);
  const [categoryData, setCategoryData] = useState<Record<string, unknown>>({});

  // Business location for context
  const [businessLocations, setBusinessLocations] = useState<BusinessLocation[]>([]);
  const [selectedLocationId, setSelectedLocationId] = useState<string>('');

  // Involved employees
  const [companyEmployees, setCompanyEmployees] = useState<{id: string; first_name: string; last_name: string}[]>([]);
  const [involvedEmployeeIds, setInvolvedEmployeeIds] = useState<string[]>([]);
  const [employeePickerValue, setEmployeePickerValue] = useState('');

  useEffect(() => {
    complianceAPI.getLocations().then(setBusinessLocations).catch(() => {
      // Locations may not be available if compliance feature isn't enabled
    });
    // Fetch employees for the involved employees picker
    const token = getAccessToken();
    if (token) {
      fetch(`${API_BASE}/employees`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => setCompanyEmployees(data))
        .catch(() => {});
    }
  }, []);

  const updateCategory = (field: string, value: unknown) => {
    setCategoryData({ ...categoryData, [field]: value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !occurredAt || !reportedByName.trim()) {
      setError('Fill required fields');
      return;
    }

    setCreating(true);
    setError(null);

    try {
      // Derive company_id from the selected location
      const selectedLocation = businessLocations.find((loc) => loc.id === selectedLocationId);
      const companyId = selectedLocation?.company_id;

      const data: IRIncidentCreate = {
        title: title.trim(),
        description: description.trim() || undefined,
        incident_type: incidentType,
        severity,
        occurred_at: new Date(occurredAt).toISOString(),
        location: location.trim() || undefined,
        reported_by_name: reportedByName.trim(),
        reported_by_email: reportedByEmail.trim() || undefined,
        witnesses: witnesses.filter((w) => w.name.trim()),
        category_data: Object.keys(categoryData).length > 0 ? categoryData : undefined,
        company_id: companyId || undefined,
        location_id: selectedLocationId || undefined,
        involved_employee_ids: involvedEmployeeIds.length > 0 ? involvedEmployeeIds : undefined,
      };

      const created = await irIncidents.createIncident(data);
      navigate(`/app/ir/incidents/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${th.pageBg}`}>
    <div className="max-w-xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className={`${th.btnGhost} text-xs uppercase tracking-wider mb-6 flex items-center gap-1 font-bold`}
      >
        <span>&larr;</span> Back
      </button>

      <div className="flex items-center gap-3 mb-12 pb-8">
        <h1 className={`text-4xl font-bold tracking-tighter ${th.textMain} uppercase`}>New Incident</h1>
        <FeatureGuideTrigger guideId="ir-create" />
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        {error && <div className="text-xs text-red-400 px-4 py-3 border border-red-500/40 bg-red-950/30 rounded-xl font-mono uppercase tracking-wider">{error}</div>}

        {/* Type & Severity - inline */}
        <div className="flex gap-8">
          <div data-tour="ir-create-type" className="flex-1">
            <div className={`${th.label} mb-2`}>Type</div>
            <div className="flex gap-1 flex-wrap">
              {TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => { setIncidentType(t.value); setCategoryData({}); }}
                  className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                    incidentType === t.value ? th.chipActive : th.chipInactive
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div data-tour="ir-create-severity">
            <div className={`${th.label} mb-2`}>Severity</div>
            <div className="flex gap-1">
              {SEVERITIES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setSeverity(s.value)}
                  className={`w-7 h-7 rounded-full flex items-center justify-center transition-all ${
                    severity === s.value ? `ring-2 ${isLight ? 'ring-zinc-900' : 'ring-white'} ring-offset-2 ${th.sevRing}` : ''
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full ${th.sevDots[s.value]}`} />
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Title */}
        <div data-tour="ir-create-title">
          <div className={`${th.label} mb-2`}>What happened *</div>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Brief description"
            className={th.input}
            required
          />
        </div>

        {/* Description */}
        <div>
          <div className={`${th.label} mb-2`}>Details</div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Full account of the incident..."
            rows={2}
            className={th.textarea}
          />
        </div>

        {/* When & Where */}
        <div className="grid grid-cols-2 gap-6">
          <div data-tour="ir-create-when">
            <div className={`${th.label} mb-2`}>When *</div>
            <input
              type="datetime-local"
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
              className={th.input}
              required
            />
          </div>
          <div data-tour="ir-create-where">
            <div className={`${th.label} mb-2`}>Where</div>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Specific location (e.g., Warehouse B)"
              className={th.input}
            />
          </div>
        </div>

        {/* Business Location */}
        {businessLocations.length > 0 && (
          <div>
            <div className={`${th.label} mb-2`}>Business Location</div>
            <select
              value={selectedLocationId}
              onChange={(e) => setSelectedLocationId(e.target.value)}
              className={th.select}
            >
              <option value="">Select location...</option>
              {businessLocations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name ? `${loc.name} - ` : ''}{loc.city}, {loc.state}
                </option>
              ))}
            </select>
            <div className={`text-[10px] ${th.textFaint} mt-1`}>
              Links to company location for compliance context
            </div>
          </div>
        )}

        {/* Category-specific fields */}
        {incidentType === 'safety' && (
          <div className={`space-y-4 pt-4 border-t ${th.sectionBorder}`}>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className={`${th.label} mb-2`}>Injured person</div>
                <input
                  type="text"
                  value={(categoryData.injured_person as string) || ''}
                  onChange={(e) => updateCategory('injured_person', e.target.value)}
                  placeholder="Name"
                  className={th.input}
                />
              </div>
              <div>
                <div className={`${th.label} mb-2`}>Injury type</div>
                <div className="flex gap-1 flex-wrap">
                  {INJURY_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => updateCategory('injury_type', t.toLowerCase())}
                      className={`px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                        categoryData.injury_type === t.toLowerCase()
                          ? th.chipActive
                          : th.chipInactive
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className={`${th.label} mb-2`}>Body part</div>
                <div className="flex gap-1 flex-wrap">
                  {BODY_PARTS.map((p) => {
                    const selected = ((categoryData.body_parts as string[]) || []).includes(p);
                    return (
                      <button
                        key={p}
                        type="button"
                        onClick={() => {
                          const current = (categoryData.body_parts as string[]) || [];
                          updateCategory('body_parts', selected ? current.filter((x) => x !== p) : [...current, p]);
                        }}
                        className={`px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                          selected ? th.chipActive : th.chipInactive
                        }`}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <div className={`${th.label} mb-2`}>Treatment</div>
                <div className="flex gap-1 flex-wrap">
                  {TREATMENTS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => updateCategory('treatment', t.toLowerCase().replace(' ', '_'))}
                      className={`px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                        categoryData.treatment === t.toLowerCase().replace(' ', '_')
                          ? th.chipActive
                          : th.chipInactive
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <label data-tour="ir-osha-recordable" className={`flex items-center gap-2 text-xs ${th.textMuted} cursor-pointer`}>
              <input
                type="checkbox"
                checked={(categoryData.osha_recordable as boolean) || false}
                onChange={(e) => updateCategory('osha_recordable', e.target.checked)}
                className={`w-3 h-3 rounded ${th.checkboxBg}`}
              />
              OSHA recordable
            </label>
          </div>
        )}

        {incidentType === 'behavioral' && (
          <div className={`space-y-4 pt-4 border-t ${th.sectionBorder}`}>
            <div>
              <div className={`${th.label} mb-2`}>Policy violated</div>
              <input
                type="text"
                value={(categoryData.policy_violated as string) || ''}
                onChange={(e) => updateCategory('policy_violated', e.target.value)}
                placeholder="e.g., Code of Conduct 3.2"
                className={th.input}
              />
            </div>
            <label className={`flex items-center gap-2 text-xs ${th.textMuted} cursor-pointer`}>
              <input
                type="checkbox"
                checked={(categoryData.manager_notified as boolean) || false}
                onChange={(e) => updateCategory('manager_notified', e.target.checked)}
                className={`w-3 h-3 rounded ${th.checkboxBg}`}
              />
              Manager notified
            </label>
          </div>
        )}

        {incidentType === 'property' && (
          <div className={`space-y-4 pt-4 border-t ${th.sectionBorder}`}>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className={`${th.label} mb-2`}>Asset damaged</div>
                <input
                  type="text"
                  value={(categoryData.asset_damaged as string) || ''}
                  onChange={(e) => updateCategory('asset_damaged', e.target.value)}
                  placeholder="Description"
                  className={th.input}
                />
              </div>
              <div>
                <div className={`${th.label} mb-2`}>Est. cost ($)</div>
                <input
                  type="number"
                  min="0"
                  value={(categoryData.estimated_cost as number) || ''}
                  onChange={(e) => updateCategory('estimated_cost', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="0"
                  className={th.input}
                />
              </div>
            </div>
            <label className={`flex items-center gap-2 text-xs ${th.textMuted} cursor-pointer`}>
              <input
                type="checkbox"
                checked={(categoryData.insurance_claim as boolean) || false}
                onChange={(e) => updateCategory('insurance_claim', e.target.checked)}
                className={`w-3 h-3 rounded ${th.checkboxBg}`}
              />
              Insurance claim needed
            </label>
          </div>
        )}

        {incidentType === 'near_miss' && (
          <div className={`space-y-4 pt-4 border-t ${th.sectionBorder}`}>
            <div>
              <div className={`${th.label} mb-2`}>Potential outcome</div>
              <input
                type="text"
                value={(categoryData.potential_outcome as string) || ''}
                onChange={(e) => updateCategory('potential_outcome', e.target.value)}
                placeholder="What could have happened"
                className={th.input}
              />
            </div>
            <div>
              <div className={`${th.label} mb-2`}>Hazard identified</div>
              <input
                type="text"
                value={(categoryData.hazard_identified as string) || ''}
                onChange={(e) => updateCategory('hazard_identified', e.target.value)}
                placeholder="Description"
                className={th.input}
              />
            </div>
          </div>
        )}

        {/* Reporter */}
        <div className={`pt-4 border-t ${th.sectionBorder}`}>
          <div className={`${th.label} mb-2`}>Reporter</div>
          <div className="grid grid-cols-2 gap-6">
            <input
              type="text"
              value={reportedByName}
              onChange={(e) => setReportedByName(e.target.value)}
              placeholder="Name *"
              className={th.input}
              required
            />
            <input
              type="email"
              value={reportedByEmail}
              onChange={(e) => setReportedByEmail(e.target.value)}
              placeholder="Email"
              className={th.input}
            />
          </div>
        </div>

        {/* Involved Employees */}
        {companyEmployees.length > 0 && (
          <div>
            <div className={`${th.label} mb-2`}>Involved Employees</div>
            <div className="flex gap-2 items-center">
              <select
                value={employeePickerValue}
                onChange={(e) => setEmployeePickerValue(e.target.value)}
                className={`flex-1 ${th.select}`}
              >
                <option value="">Select employee...</option>
                {companyEmployees
                  .filter((emp) => !involvedEmployeeIds.includes(emp.id))
                  .map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.first_name} {emp.last_name}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  if (employeePickerValue && !involvedEmployeeIds.includes(employeePickerValue)) {
                    setInvolvedEmployeeIds([...involvedEmployeeIds, employeePickerValue]);
                    setEmployeePickerValue('');
                  }
                }}
                disabled={!employeePickerValue}
                className={`text-[10px] ${th.btnGhost} uppercase tracking-wider font-bold disabled:opacity-30`}
              >
                + Add
              </button>
            </div>
            {involvedEmployeeIds.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {involvedEmployeeIds.map((empId) => {
                  const emp = companyEmployees.find((e) => e.id === empId);
                  return (
                    <span
                      key={empId}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${th.chipActive}`}
                    >
                      {emp ? `${emp.first_name} ${emp.last_name}` : empId}
                      <button
                        type="button"
                        onClick={() => setInvolvedEmployeeIds(involvedEmployeeIds.filter((id) => id !== empId))}
                        className="hover:opacity-70"
                      >
                        &times;
                      </button>
                    </span>
                  );
                })}
              </div>
            )}
            <div className={`text-[10px] ${th.textFaint} mt-1`}>
              Employees directly involved in or affected by this incident
            </div>
          </div>
        )}

        {/* Witnesses */}
        <div data-tour="ir-create-witnesses">
          <div className="flex justify-between items-center">
            <div className={th.label}>Witnesses</div>
            <button
              type="button"
              onClick={() => setWitnesses([...witnesses, { name: '', contact: '' }])}
              className={`text-[10px] ${th.btnGhost} uppercase tracking-wider font-bold`}
            >
              + Add
            </button>
          </div>
          {witnesses.length === 0 ? (
            <div className={`text-xs ${th.textFaint}`}>None</div>
          ) : (
            <div className="space-y-2 mt-2">
              {witnesses.map((w, i) => (
                <div key={i} className="flex gap-4 items-center">
                  <input
                    type="text"
                    value={w.name}
                    onChange={(e) => {
                      const updated = [...witnesses];
                      updated[i] = { ...w, name: e.target.value };
                      setWitnesses(updated);
                    }}
                    placeholder="Name"
                    className={`flex-1 ${th.input}`}
                  />
                  <input
                    type="text"
                    value={w.contact || ''}
                    onChange={(e) => {
                      const updated = [...witnesses];
                      updated[i] = { ...w, contact: e.target.value };
                      setWitnesses(updated);
                    }}
                    placeholder="Contact"
                    className={`flex-1 ${th.input}`}
                  />
                  <button
                    type="button"
                    onClick={() => setWitnesses(witnesses.filter((_, idx) => idx !== i))}
                    className={`${th.btnGhost} hover:text-red-400 text-xs`}
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className={`flex justify-end gap-4 pt-8 border-t ${th.sectionBorder}`}>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={`text-xs ${th.btnGhost} uppercase tracking-wider font-bold`}
          >
            Cancel
          </button>
          <button
            data-tour="ir-create-submit"
            type="submit"
            disabled={creating}
            className={`px-5 py-2 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 ${th.btnPrimary}`}
          >
            {creating ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </form>
    </div>
    </div>
  );
}

export default IRCreate;
