import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { irIncidents } from '../api/client';
import type { IRIncidentType, IRSeverity, IRWitness, IRIncidentCreate } from '../types';

const TYPE_OPTIONS: { value: IRIncidentType; label: string; description: string }[] = [
  { value: 'safety', label: 'Safety / Injury', description: 'Physical injuries, accidents, unsafe conditions' },
  { value: 'behavioral', label: 'Behavioral / HR', description: 'Policy violations, harassment, conflicts' },
  { value: 'property', label: 'Property Damage', description: 'Damage to equipment, facilities, assets' },
  { value: 'near_miss', label: 'Near Miss', description: 'Close calls, hazards identified' },
  { value: 'other', label: 'Other', description: 'Incidents that don\'t fit other categories' },
];

const SEVERITY_OPTIONS: { value: IRSeverity; label: string; color: string }[] = [
  { value: 'critical', label: 'Critical', color: 'bg-red-600' },
  { value: 'high', label: 'High', color: 'bg-orange-500' },
  { value: 'medium', label: 'Medium', color: 'bg-yellow-500' },
  { value: 'low', label: 'Low', color: 'bg-green-500' },
];

const BODY_PARTS = [
  'Head', 'Neck', 'Shoulder', 'Arm', 'Elbow', 'Wrist', 'Hand', 'Fingers',
  'Back', 'Chest', 'Abdomen', 'Hip', 'Leg', 'Knee', 'Ankle', 'Foot', 'Toes',
];

const INJURY_TYPES = ['Cut', 'Burn', 'Strain', 'Sprain', 'Fracture', 'Contusion', 'Laceration', 'Chemical Exposure', 'Other'];
const TREATMENT_TYPES = ['First Aid', 'Medical Treatment', 'ER Visit', 'Hospitalization', 'None'];

export function IRCreate() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Base form data
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [incidentType, setIncidentType] = useState<IRIncidentType>('safety');
  const [severity, setSeverity] = useState<IRSeverity>('medium');
  const [occurredAt, setOccurredAt] = useState('');
  const [location, setLocation] = useState('');
  const [reportedByName, setReportedByName] = useState('');
  const [reportedByEmail, setReportedByEmail] = useState('');

  // Witnesses
  const [witnesses, setWitnesses] = useState<IRWitness[]>([]);

  // Category-specific data
  const [categoryData, setCategoryData] = useState<Record<string, unknown>>({});

  const addWitness = () => {
    setWitnesses([...witnesses, { name: '', contact: '', statement: '' }]);
  };

  const updateWitness = (index: number, field: keyof IRWitness, value: string) => {
    const updated = [...witnesses];
    updated[index] = { ...updated[index], [field]: value };
    setWitnesses(updated);
  };

  const removeWitness = (index: number) => {
    setWitnesses(witnesses.filter((_, i) => i !== index));
  };

  const updateCategoryData = (field: string, value: unknown) => {
    setCategoryData({ ...categoryData, [field]: value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim() || !occurredAt || !reportedByName.trim()) {
      setError('Please fill in all required fields.');
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
      console.error('Failed to create incident:', err);
      setError(err instanceof Error ? err.message : 'Failed to create incident');
    } finally {
      setCreating(false);
    }
  };

  const renderCategoryFields = () => {
    switch (incidentType) {
      case 'safety':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white">Safety / Injury Details</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Injured Person</label>
                <input
                  type="text"
                  value={(categoryData.injured_person as string) || ''}
                  onChange={(e) => updateCategoryData('injured_person', e.target.value)}
                  placeholder="Name of injured person"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Role / Position</label>
                <input
                  type="text"
                  value={(categoryData.injured_person_role as string) || ''}
                  onChange={(e) => updateCategoryData('injured_person_role', e.target.value)}
                  placeholder="Job title or role"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">Body Parts Affected</label>
              <div className="flex flex-wrap gap-2">
                {BODY_PARTS.map((part) => {
                  const selected = ((categoryData.body_parts as string[]) || []).includes(part);
                  return (
                    <button
                      key={part}
                      type="button"
                      onClick={() => {
                        const current = (categoryData.body_parts as string[]) || [];
                        const updated = selected ? current.filter((p) => p !== part) : [...current, part];
                        updateCategoryData('body_parts', updated);
                      }}
                      className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                        selected ? 'bg-matcha-500 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'
                      }`}
                    >
                      {part}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Injury Type</label>
                <select
                  value={(categoryData.injury_type as string) || ''}
                  onChange={(e) => updateCategoryData('injury_type', e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
                >
                  <option value="">Select type</option>
                  {INJURY_TYPES.map((t) => (
                    <option key={t} value={t.toLowerCase()}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Treatment Received</label>
                <select
                  value={(categoryData.treatment as string) || ''}
                  onChange={(e) => updateCategoryData('treatment', e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
                >
                  <option value="">Select treatment</option>
                  {TREATMENT_TYPES.map((t) => (
                    <option key={t} value={t.toLowerCase().replace(' ', '_')}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Lost Work Days</label>
                <input
                  type="number"
                  min="0"
                  value={(categoryData.lost_days as number) || ''}
                  onChange={(e) => updateCategoryData('lost_days', e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="0"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Equipment Involved</label>
                <input
                  type="text"
                  value={(categoryData.equipment_involved as string) || ''}
                  onChange={(e) => updateCategoryData('equipment_involved', e.target.value)}
                  placeholder="e.g., Forklift, Ladder"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>
            </div>

            <div>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(categoryData.osha_recordable as boolean) || false}
                  onChange={(e) => updateCategoryData('osha_recordable', e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-800 border-zinc-700 text-matcha-500 focus:ring-matcha-500"
                />
                OSHA Recordable Incident
              </label>
            </div>
          </div>
        );

      case 'behavioral':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white">Behavioral / HR Details</h3>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Policy Violated</label>
              <input
                type="text"
                value={(categoryData.policy_violated as string) || ''}
                onChange={(e) => updateCategoryData('policy_violated', e.target.value)}
                placeholder="e.g., Code of Conduct Section 3.2"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>

            <div>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(categoryData.manager_notified as boolean) || false}
                  onChange={(e) => updateCategoryData('manager_notified', e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-800 border-zinc-700 text-matcha-500 focus:ring-matcha-500"
                />
                Manager has been notified
              </label>
            </div>
          </div>
        );

      case 'property':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white">Property Damage Details</h3>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Asset / Equipment Damaged</label>
              <input
                type="text"
                value={(categoryData.asset_damaged as string) || ''}
                onChange={(e) => updateCategoryData('asset_damaged', e.target.value)}
                placeholder="Describe the damaged property"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Estimated Cost ($)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={(categoryData.estimated_cost as number) || ''}
                  onChange={(e) => updateCategoryData('estimated_cost', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>

              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer pb-2">
                  <input
                    type="checkbox"
                    checked={(categoryData.insurance_claim as boolean) || false}
                    onChange={(e) => updateCategoryData('insurance_claim', e.target.checked)}
                    className="w-4 h-4 rounded bg-zinc-800 border-zinc-700 text-matcha-500 focus:ring-matcha-500"
                  />
                  Insurance claim needed
                </label>
              </div>
            </div>
          </div>
        );

      case 'near_miss':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white">Near Miss Details</h3>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">What Could Have Happened?</label>
              <textarea
                value={(categoryData.potential_outcome as string) || ''}
                onChange={(e) => updateCategoryData('potential_outcome', e.target.value)}
                placeholder="Describe the potential outcome if this had resulted in an incident"
                rows={2}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Hazard Identified</label>
              <input
                type="text"
                value={(categoryData.hazard_identified as string) || ''}
                onChange={(e) => updateCategoryData('hazard_identified', e.target.value)}
                placeholder="Describe the hazard"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Immediate Action Taken</label>
              <textarea
                value={(categoryData.immediate_action as string) || ''}
                onChange={(e) => updateCategoryData('immediate_action', e.target.value)}
                placeholder="What was done immediately to address the hazard?"
                rows={2}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Suggested Preventive Measures</label>
              <textarea
                value={(categoryData.preventive_measures as string) || ''}
                onChange={(e) => updateCategoryData('preventive_measures', e.target.value)}
                placeholder="What should be done to prevent this in the future?"
                rows={2}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
              />
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate(-1)} className="text-zinc-400 hover:text-white transition-colors">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Report Incident</h1>
          <p className="text-zinc-400 mt-1">Document and track workplace incidents</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">{error}</div>
        )}

        {/* Incident Type Selection */}
        <Card className="mb-6">
          <CardContent>
            <h2 className="text-lg font-medium text-white mb-4">Incident Type</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    setIncidentType(opt.value);
                    setCategoryData({});
                  }}
                  className={`p-4 text-left rounded-lg border transition-colors ${
                    incidentType === opt.value
                      ? 'border-matcha-500 bg-matcha-500/10'
                      : 'border-zinc-700 hover:border-zinc-600'
                  }`}
                >
                  <div className="font-medium text-white">{opt.label}</div>
                  <div className="text-sm text-zinc-500">{opt.description}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Basic Information */}
        <Card className="mb-6">
          <CardContent>
            <h2 className="text-lg font-medium text-white mb-4">Basic Information</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Title *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Brief description of the incident"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Detailed account of what happened..."
                  rows={4}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">When did it occur? *</label>
                  <input
                    type="datetime-local"
                    value={occurredAt}
                    onChange={(e) => setOccurredAt(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">Location</label>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g., Warehouse Floor B, Building 2"
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">Severity</label>
                <div className="flex gap-2">
                  {SEVERITY_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setSeverity(opt.value)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${
                        severity === opt.value
                          ? 'border-white bg-zinc-800'
                          : 'border-zinc-700 hover:border-zinc-600'
                      }`}
                    >
                      <div className={`w-3 h-3 rounded-full ${opt.color}`} />
                      <span className="text-white">{opt.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Category-Specific Fields */}
        <Card className="mb-6">
          <CardContent>{renderCategoryFields()}</CardContent>
        </Card>

        {/* Reporter Information */}
        <Card className="mb-6">
          <CardContent>
            <h2 className="text-lg font-medium text-white mb-4">Reporter Information</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Reported By *</label>
                <input
                  type="text"
                  value={reportedByName}
                  onChange={(e) => setReportedByName(e.target.value)}
                  placeholder="Your name"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Email</label>
                <input
                  type="email"
                  value={reportedByEmail}
                  onChange={(e) => setReportedByEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Witnesses */}
        <Card className="mb-6">
          <CardContent>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-medium text-white">Witnesses</h2>
              <Button type="button" variant="outline" size="sm" onClick={addWitness}>
                Add Witness
              </Button>
            </div>

            {witnesses.length === 0 ? (
              <div className="text-sm text-zinc-500">No witnesses added</div>
            ) : (
              <div className="space-y-4">
                {witnesses.map((witness, idx) => (
                  <div key={idx} className="p-4 bg-zinc-800/50 rounded-lg">
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-sm text-zinc-400">Witness {idx + 1}</span>
                      <button
                        type="button"
                        onClick={() => removeWitness(idx)}
                        className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
                      >
                        Remove
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <input
                        type="text"
                        value={witness.name}
                        onChange={(e) => updateWitness(idx, 'name', e.target.value)}
                        placeholder="Name"
                        className="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                      />
                      <input
                        type="text"
                        value={witness.contact || ''}
                        onChange={(e) => updateWitness(idx, 'contact', e.target.value)}
                        placeholder="Contact (phone/email)"
                        className="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                      />
                    </div>

                    <textarea
                      value={witness.statement || ''}
                      onChange={(e) => updateWitness(idx, 'statement', e.target.value)}
                      placeholder="Witness statement..."
                      rows={2}
                      className="mt-3 w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-white"
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Cancel
          </Button>
          <Button type="submit" disabled={creating}>
            {creating ? 'Creating...' : 'Submit Report'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default IRCreate;
