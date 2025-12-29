import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRIncidentType, IRSeverity, IRWitness, IRIncidentCreate } from '../types';

const TYPES: { value: IRIncidentType; label: string }[] = [
  { value: 'safety', label: 'Safety' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'property', label: 'Property' },
  { value: 'near_miss', label: 'Near Miss' },
  { value: 'other', label: 'Other' },
];

const SEVERITIES: { value: IRSeverity; color: string }[] = [
  { value: 'low', color: 'bg-green-500' },
  { value: 'medium', color: 'bg-yellow-500' },
  { value: 'high', color: 'bg-orange-500' },
  { value: 'critical', color: 'bg-red-600' },
];

const BODY_PARTS = ['Head', 'Neck', 'Back', 'Arm', 'Hand', 'Leg', 'Foot', 'Other'];
const INJURY_TYPES = ['Cut', 'Burn', 'Strain', 'Fracture', 'Contusion', 'Other'];
const TREATMENTS = ['None', 'First Aid', 'Medical', 'ER', 'Hospital'];

export function IRCreate() {
  const navigate = useNavigate();
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
      };

      const created = await irIncidents.createIncident(data);
      navigate(`/app/ir/incidents/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    } finally {
      setCreating(false);
    }
  };

  const inputClass = 'w-full px-2.5 py-1.5 bg-transparent border-b border-zinc-800 text-white text-sm placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors';
  const labelClass = 'text-[10px] uppercase tracking-wider text-zinc-600 mb-1';

  return (
    <div className="max-w-xl mx-auto py-8">
      <button
        onClick={() => navigate(-1)}
        className="text-zinc-600 hover:text-white text-xs uppercase tracking-wider mb-6 flex items-center gap-1"
      >
        <span>←</span> Back
      </button>

      <h1 className="text-lg font-medium text-white mb-8">New Incident Report</h1>

      <form onSubmit={handleSubmit} className="space-y-8">
        {error && <div className="text-xs text-red-400">{error}</div>}

        {/* Type & Severity - inline */}
        <div className="flex gap-8">
          <div className="flex-1">
            <div className={labelClass}>Type</div>
            <div className="flex gap-1 flex-wrap">
              {TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => { setIncidentType(t.value); setCategoryData({}); }}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    incidentType === t.value
                      ? 'bg-white text-black'
                      : 'text-zinc-500 hover:text-white'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className={labelClass}>Severity</div>
            <div className="flex gap-1">
              {SEVERITIES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setSeverity(s.value)}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                    severity === s.value ? 'ring-2 ring-white ring-offset-2 ring-offset-zinc-950' : ''
                  }`}
                >
                  <div className={`w-3 h-3 rounded-full ${s.color}`} />
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Title */}
        <div>
          <div className={labelClass}>What happened *</div>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Brief description"
            className={inputClass}
            required
          />
        </div>

        {/* Description */}
        <div>
          <div className={labelClass}>Details</div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Full account of the incident..."
            rows={2}
            className={`${inputClass} resize-none`}
          />
        </div>

        {/* When & Where */}
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className={labelClass}>When *</div>
            <input
              type="datetime-local"
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
              className={inputClass}
              required
            />
          </div>
          <div>
            <div className={labelClass}>Where</div>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Location"
              className={inputClass}
            />
          </div>
        </div>

        {/* Category-specific fields */}
        {incidentType === 'safety' && (
          <div className="space-y-4 pt-4 border-t border-zinc-900">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className={labelClass}>Injured person</div>
                <input
                  type="text"
                  value={(categoryData.injured_person as string) || ''}
                  onChange={(e) => updateCategory('injured_person', e.target.value)}
                  placeholder="Name"
                  className={inputClass}
                />
              </div>
              <div>
                <div className={labelClass}>Injury type</div>
                <div className="flex gap-1 flex-wrap">
                  {INJURY_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => updateCategory('injury_type', t.toLowerCase())}
                      className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                        categoryData.injury_type === t.toLowerCase()
                          ? 'bg-zinc-700 text-white'
                          : 'text-zinc-600 hover:text-white'
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
                <div className={labelClass}>Body part</div>
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
                        className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                          selected ? 'bg-zinc-700 text-white' : 'text-zinc-600 hover:text-white'
                        }`}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <div className={labelClass}>Treatment</div>
                <div className="flex gap-1 flex-wrap">
                  {TREATMENTS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => updateCategory('treatment', t.toLowerCase().replace(' ', '_'))}
                      className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                        categoryData.treatment === t.toLowerCase().replace(' ', '_')
                          ? 'bg-zinc-700 text-white'
                          : 'text-zinc-600 hover:text-white'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">
              <input
                type="checkbox"
                checked={(categoryData.osha_recordable as boolean) || false}
                onChange={(e) => updateCategory('osha_recordable', e.target.checked)}
                className="w-3 h-3 rounded bg-zinc-900 border-zinc-700"
              />
              OSHA recordable
            </label>
          </div>
        )}

        {incidentType === 'behavioral' && (
          <div className="space-y-4 pt-4 border-t border-zinc-900">
            <div>
              <div className={labelClass}>Policy violated</div>
              <input
                type="text"
                value={(categoryData.policy_violated as string) || ''}
                onChange={(e) => updateCategory('policy_violated', e.target.value)}
                placeholder="e.g., Code of Conduct 3.2"
                className={inputClass}
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">
              <input
                type="checkbox"
                checked={(categoryData.manager_notified as boolean) || false}
                onChange={(e) => updateCategory('manager_notified', e.target.checked)}
                className="w-3 h-3 rounded bg-zinc-900 border-zinc-700"
              />
              Manager notified
            </label>
          </div>
        )}

        {incidentType === 'property' && (
          <div className="space-y-4 pt-4 border-t border-zinc-900">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className={labelClass}>Asset damaged</div>
                <input
                  type="text"
                  value={(categoryData.asset_damaged as string) || ''}
                  onChange={(e) => updateCategory('asset_damaged', e.target.value)}
                  placeholder="Description"
                  className={inputClass}
                />
              </div>
              <div>
                <div className={labelClass}>Est. cost ($)</div>
                <input
                  type="number"
                  min="0"
                  value={(categoryData.estimated_cost as number) || ''}
                  onChange={(e) => updateCategory('estimated_cost', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="0"
                  className={inputClass}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">
              <input
                type="checkbox"
                checked={(categoryData.insurance_claim as boolean) || false}
                onChange={(e) => updateCategory('insurance_claim', e.target.checked)}
                className="w-3 h-3 rounded bg-zinc-900 border-zinc-700"
              />
              Insurance claim needed
            </label>
          </div>
        )}

        {incidentType === 'near_miss' && (
          <div className="space-y-4 pt-4 border-t border-zinc-900">
            <div>
              <div className={labelClass}>Potential outcome</div>
              <input
                type="text"
                value={(categoryData.potential_outcome as string) || ''}
                onChange={(e) => updateCategory('potential_outcome', e.target.value)}
                placeholder="What could have happened"
                className={inputClass}
              />
            </div>
            <div>
              <div className={labelClass}>Hazard identified</div>
              <input
                type="text"
                value={(categoryData.hazard_identified as string) || ''}
                onChange={(e) => updateCategory('hazard_identified', e.target.value)}
                placeholder="Description"
                className={inputClass}
              />
            </div>
          </div>
        )}

        {/* Reporter */}
        <div className="pt-4 border-t border-zinc-900">
          <div className={labelClass}>Reporter</div>
          <div className="grid grid-cols-2 gap-6">
            <input
              type="text"
              value={reportedByName}
              onChange={(e) => setReportedByName(e.target.value)}
              placeholder="Name *"
              className={inputClass}
              required
            />
            <input
              type="email"
              value={reportedByEmail}
              onChange={(e) => setReportedByEmail(e.target.value)}
              placeholder="Email"
              className={inputClass}
            />
          </div>
        </div>

        {/* Witnesses */}
        <div>
          <div className="flex justify-between items-center">
            <div className={labelClass}>Witnesses</div>
            <button
              type="button"
              onClick={() => setWitnesses([...witnesses, { name: '', contact: '' }])}
              className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
            >
              + Add
            </button>
          </div>
          {witnesses.length === 0 ? (
            <div className="text-xs text-zinc-700">None</div>
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
                    className="flex-1 px-2 py-1 bg-transparent border-b border-zinc-800 text-white text-xs placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
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
                    className="flex-1 px-2 py-1 bg-transparent border-b border-zinc-800 text-white text-xs placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
                  />
                  <button
                    type="button"
                    onClick={() => setWitnesses(witnesses.filter((_, idx) => idx !== i))}
                    className="text-zinc-700 hover:text-red-400 text-xs"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-4 pt-8 border-t border-zinc-900">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-2 bg-white text-black text-xs font-medium rounded hover:bg-zinc-200 disabled:opacity-50 uppercase tracking-wider"
          >
            {creating ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default IRCreate;
