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
          <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  if (error || !employee) {
    return (
      <div className="p-6">
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 font-mono text-sm uppercase">{error || 'Failed to load profile'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white uppercase">My Profile</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">View and update your personal information</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 px-6 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      {/* Read-only Info */}
      <div className="bg-zinc-900/30 border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Employment Information</h2>
        </div>
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          <div className="flex items-center gap-4 group">
            <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
              <User className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
            </div>
            <div>
              <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">Full Name</span>
              <div className="text-sm font-bold text-white tracking-tight">{employee.first_name} {employee.last_name}</div>
            </div>
          </div>
          <div className="flex items-center gap-4 group">
            <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
              <Building className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
            </div>
            <div>
              <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">Employment Type</span>
              <div className="text-sm font-bold text-white tracking-tight">{formatEmploymentType(employee.employment_type)}</div>
            </div>
          </div>
          <div className="flex items-center gap-4 group">
            <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
              <MapPin className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
            </div>
            <div>
              <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">Work State</span>
              <div className="text-sm font-bold text-white tracking-tight">{employee.work_state || 'N/A'}</div>
            </div>
          </div>
          <div className="flex items-center gap-4 group">
            <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
              <Calendar className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
            </div>
            <div>
              <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">Start Date</span>
              <div className="text-sm font-bold text-white tracking-tight">
                {employee.start_date ? new Date(employee.start_date).toLocaleDateString() : 'N/A'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Editable Contact Info */}
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Contact Information</h2>
          </div>
          <div className="p-6 space-y-6">
            <div>
              <label className="block text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-2 ml-1">Email</label>
              <input
                type="email"
                value={employee.email}
                disabled
                className="w-full bg-zinc-950 border border-zinc-800 text-zinc-500 px-4 py-3 text-sm font-mono cursor-not-allowed opacity-50"
              />
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 ml-1">Contact HR to change your email address</p>
            </div>
            <div>
              <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Phone Number</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="Enter phone number"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
              />
            </div>
            <div>
              <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Address</label>
              <textarea
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Enter your address"
                rows={4}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none font-mono leading-relaxed"
              />
            </div>
          </div>
        </div>

        {/* Emergency Contact */}
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Emergency Contact</h2>
          </div>
          <div className="p-6 space-y-6">
            <div>
              <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Full Name</label>
              <input
                type="text"
                value={emergencyName}
                onChange={(e) => setEmergencyName(e.target.value)}
                placeholder="Contact name"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
              />
            </div>
            <div>
              <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Phone</label>
              <input
                type="tel"
                value={emergencyPhone}
                onChange={(e) => setEmergencyPhone(e.target.value)}
                placeholder="Contact phone"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
              />
            </div>
            <div>
              <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Relationship</label>
              <input
                type="text"
                value={emergencyRelationship}
                onChange={(e) => setEmergencyRelationship(e.target.value)}
                placeholder="e.g., Spouse, Parent"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PortalProfile;
