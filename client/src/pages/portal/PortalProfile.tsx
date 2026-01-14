import { useEffect, useState } from 'react';
import { User, Building, MapPin, Calendar, AlertCircle, Save } from 'lucide-react';
import { portalApi } from '../../api/portal';

interface Employee {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  work_state: string | null;
  employment_type: string | null;
  start_date: string | null;
  phone: string | null;
  address: string | null;
  emergency_contact: {
    name?: string;
    phone?: string;
    relationship?: string;
  } | null;
}

export function PortalProfile() {
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Editable fields
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [emergencyName, setEmergencyName] = useState('');
  const [emergencyPhone, setEmergencyPhone] = useState('');
  const [emergencyRelationship, setEmergencyRelationship] = useState('');

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await portalApi.getDashboard();
        setEmployee(data.employee);
        setPhone(data.employee.phone || '');
        setAddress(data.employee.address || '');
        if (data.employee.emergency_contact) {
          setEmergencyName(data.employee.emergency_contact.name || '');
          setEmergencyPhone(data.employee.emergency_contact.phone || '');
          setEmergencyRelationship(data.employee.emergency_contact.relationship || '');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load profile');
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await portalApi.updateProfile({
        phone: phone || undefined,
        address: address || undefined,
        emergency_contact: {
          name: emergencyName || undefined,
          phone: emergencyPhone || undefined,
          relationship: emergencyRelationship || undefined,
        },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const formatEmploymentType = (type: string | null) => {
    if (!type) return 'N/A';
    return type.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  if (error || !employee) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error || 'Failed to load profile'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-mono font-medium text-zinc-900">My Profile</h1>
          <p className="text-sm text-zinc-500 mt-1">View and update your personal information</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      {/* Read-only Info */}
      <div className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Employment Information</h2>
        </div>
        <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <User className="w-5 h-5 text-zinc-600" />
            </div>
            <div>
              <span className="text-xs text-zinc-500 font-mono uppercase">Full Name</span>
              <div className="font-medium text-zinc-900">{employee.first_name} {employee.last_name}</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <Building className="w-5 h-5 text-zinc-600" />
            </div>
            <div>
              <span className="text-xs text-zinc-500 font-mono uppercase">Employment Type</span>
              <div className="font-medium text-zinc-900">{formatEmploymentType(employee.employment_type)}</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <MapPin className="w-5 h-5 text-zinc-600" />
            </div>
            <div>
              <span className="text-xs text-zinc-500 font-mono uppercase">Work State</span>
              <div className="font-medium text-zinc-900">{employee.work_state || 'N/A'}</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-zinc-600" />
            </div>
            <div>
              <span className="text-xs text-zinc-500 font-mono uppercase">Start Date</span>
              <div className="font-medium text-zinc-900">
                {employee.start_date ? new Date(employee.start_date).toLocaleDateString() : 'N/A'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Editable Contact Info */}
      <div className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Contact Information</h2>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Email</label>
            <input
              type="email"
              value={employee.email}
              disabled
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg bg-zinc-50 text-zinc-500"
            />
            <p className="text-xs text-zinc-400 mt-1">Contact HR to change your email address</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Phone Number</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Enter phone number"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Address</label>
            <textarea
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Enter your address"
              rows={3}
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-none"
            />
          </div>
        </div>
      </div>

      {/* Emergency Contact */}
      <div className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Emergency Contact</h2>
        </div>
        <div className="p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Name</label>
            <input
              type="text"
              value={emergencyName}
              onChange={(e) => setEmergencyName(e.target.value)}
              placeholder="Contact name"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Phone</label>
            <input
              type="tel"
              value={emergencyPhone}
              onChange={(e) => setEmergencyPhone(e.target.value)}
              placeholder="Contact phone"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-2">Relationship</label>
            <input
              type="text"
              value={emergencyRelationship}
              onChange={(e) => setEmergencyRelationship(e.target.value)}
              placeholder="e.g., Spouse, Parent"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default PortalProfile;
