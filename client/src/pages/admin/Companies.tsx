import { useState, useEffect, useCallback } from 'react';
import { adminCompanies } from '../../api/client';
import type { AdminCompany, AdminCompanyDetail } from '../../api/client';
import { Building2, Users, Copy, Check, X, Pencil, ChevronRight } from 'lucide-react';

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900 border border-white/10 rounded-xl',
  innerEl: 'bg-zinc-800 rounded-lg',
  textMain: 'text-zinc-100',
  textDim: 'text-zinc-300',
  textMuted: 'text-zinc-400',
  textFaint: 'text-zinc-500',
  border: 'border-white/10',
  rowHover: 'hover:bg-white/5',
  input: 'bg-zinc-800 border border-white/10 rounded-lg text-zinc-100 text-sm px-3 py-1.5 focus:outline-none focus:border-white/30 w-full',
  select: 'bg-zinc-800 border border-white/10 rounded-lg text-zinc-100 text-sm px-3 py-1.5 focus:outline-none focus:border-white/30 w-full cursor-pointer',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btn: 'bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-xs px-3 py-1.5 rounded-lg transition',
  btnPrimary: 'bg-zinc-100 hover:bg-white text-zinc-900 text-xs px-3 py-1.5 rounded-lg transition font-medium',
  badge: 'text-[10px] px-2 py-0.5 rounded-full border font-medium',
} as const;

const INDUSTRY_OPTIONS = [
  { value: 'healthcare', label: 'Healthcare' },
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
];

const HEALTHCARE_SPECIALTIES = [
  { value: 'oncology', label: 'Oncology' },
  { value: 'primary_care', label: 'Primary Care' },
  { value: 'cardiology', label: 'Cardiology' },
  { value: 'pediatrics', label: 'Pediatrics' },
  { value: 'dermatology', label: 'Dermatology' },
  { value: 'orthopedics', label: 'Orthopedics' },
  { value: 'neurology', label: 'Neurology' },
  { value: 'psychiatry', label: 'Psychiatry' },
  { value: 'radiology', label: 'Radiology' },
  { value: 'emergency', label: 'Emergency Medicine' },
  { value: 'surgery', label: 'Surgery' },
  { value: 'obstetrics', label: 'Obstetrics / GYN' },
  { value: 'ophthalmology', label: 'Ophthalmology' },
  { value: 'urology', label: 'Urology' },
  { value: 'rheumatology', label: 'Rheumatology' },
  { value: 'endocrinology', label: 'Endocrinology' },
];

const SIZE_OPTIONS = [
  { value: '1-10', label: '1–10' },
  { value: '11-50', label: '11–50' },
  { value: '51-200', label: '51–200' },
  { value: '201-500', label: '201–500' },
  { value: '501-1000', label: '501–1000' },
  { value: '1001+', label: '1001+' },
];

function statusBadge(status: string) {
  if (status === 'pending') return `${DK.badge} border-amber-500/30 text-amber-400 bg-amber-500/10`;
  if (status === 'rejected') return `${DK.badge} border-red-500/30 text-red-400 bg-red-500/10`;
  return `${DK.badge} border-emerald-500/30 text-emerald-400 bg-emerald-500/10`;
}

function CopyId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={copy} className="flex items-center gap-1.5 group">
      <span className="font-mono text-[11px] text-zinc-500 group-hover:text-zinc-300 transition truncate max-w-[200px]">{id}</span>
      {copied ? <Check className="w-3 h-3 text-emerald-400 flex-shrink-0" /> : <Copy className="w-3 h-3 text-zinc-600 group-hover:text-zinc-400 flex-shrink-0 transition" />}
    </button>
  );
}

function CompanyDrawer({
  company,
  onClose,
  onUpdated,
}: {
  company: AdminCompanyDetail;
  onClose: () => void;
  onUpdated: (updated: AdminCompanyDetail) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: company.name ?? '',
    industry: company.industry ?? '',
    healthcare_specialties: company.healthcare_specialties ?? [],
    size: company.size ?? '',
    headquarters_city: company.headquarters_city ?? '',
    headquarters_state: company.headquarters_state ?? '',
  });

  const toggleSpecialty = (val: string) => {
    setForm(f => ({
      ...f,
      healthcare_specialties: f.healthcare_specialties.includes(val)
        ? f.healthcare_specialties.filter(s => s !== val)
        : [...f.healthcare_specialties, val],
    }));
  };

  const save = async () => {
    setSaving(true);
    try {
      await adminCompanies.update(company.id, {
        name: form.name.trim() || undefined,
        industry: form.industry || undefined,
        healthcare_specialties: form.industry === 'healthcare' ? form.healthcare_specialties : [],
        size: form.size || undefined,
        headquarters_city: form.headquarters_city.trim() || undefined,
        headquarters_state: form.headquarters_state.trim() || undefined,
      });
      onUpdated({
        ...company,
        name: form.name,
        industry: form.industry,
        healthcare_specialties: form.industry === 'healthcare' ? form.healthcare_specialties : [],
        size: form.size,
        headquarters_city: form.headquarters_city,
        headquarters_state: form.headquarters_state,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/50" onClick={onClose} />
      <div className={`w-[480px] h-full overflow-y-auto ${DK.pageBg} border-l ${DK.border} flex flex-col`}>
        {/* Header */}
        <div className={`flex items-start justify-between gap-3 p-5 border-b ${DK.border}`}>
          <div className="min-w-0">
            <h2 className={`text-base font-semibold ${DK.textMain} truncate`}>{company.name}</h2>
            <CopyId id={company.id} />
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {!editing && (
              <button onClick={() => setEditing(true)} className={DK.btn}>
                <Pencil className="w-3.5 h-3.5" />
              </button>
            )}
            <button onClick={onClose} className={`${DK.btn} !px-2`}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-5 space-y-6 flex-1">
          {/* Profile */}
          <section className="space-y-3">
            <div className={DK.label}>Profile</div>
            {editing ? (
              <div className="space-y-3">
                <div>
                  <label className={`${DK.label} mb-1 block`}>Company Name</label>
                  <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={DK.input} />
                </div>
                <div>
                  <label className={`${DK.label} mb-1 block`}>Industry</label>
                  <select value={form.industry} onChange={e => setForm(f => ({ ...f, industry: e.target.value, healthcare_specialties: [] }))} className={DK.select}>
                    <option value="">— select —</option>
                    {INDUSTRY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                {form.industry === 'healthcare' && (
                  <div>
                    <label className={`${DK.label} mb-2 block`}>Healthcare Specialties</label>
                    <div className="flex flex-wrap gap-2">
                      {HEALTHCARE_SPECIALTIES.map(s => (
                        <button
                          key={s.value}
                          type="button"
                          onClick={() => toggleSpecialty(s.value)}
                          className={`text-[11px] px-2.5 py-1 rounded-full border transition ${
                            form.healthcare_specialties.includes(s.value)
                              ? 'border-violet-500/50 bg-violet-500/15 text-violet-300'
                              : 'border-white/10 text-zinc-500 hover:border-white/20 hover:text-zinc-300'
                          }`}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <label className={`${DK.label} mb-1 block`}>Size</label>
                  <select value={form.size} onChange={e => setForm(f => ({ ...f, size: e.target.value }))} className={DK.select}>
                    <option value="">— select —</option>
                    {SIZE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={`${DK.label} mb-1 block`}>City</label>
                    <input value={form.headquarters_city} onChange={e => setForm(f => ({ ...f, headquarters_city: e.target.value }))} className={DK.input} />
                  </div>
                  <div>
                    <label className={`${DK.label} mb-1 block`}>State</label>
                    <input value={form.headquarters_state} onChange={e => setForm(f => ({ ...f, headquarters_state: e.target.value }))} className={DK.input} maxLength={2} placeholder="CA" />
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={save} disabled={saving} className={DK.btnPrimary}>
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                  <button onClick={() => setEditing(false)} className={DK.btn}>Cancel</button>
                </div>
              </div>
            ) : (
              <div className={`${DK.innerEl} p-4 space-y-3`}>
                <Row label="Industry" value={
                  company.industry
                    ? INDUSTRY_OPTIONS.find(o => o.value === company.industry)?.label ?? company.industry
                    : '—'
                } />
                {company.industry === 'healthcare' && company.healthcare_specialties.length > 0 && (
                  <div>
                    <div className={`text-[10px] ${DK.textFaint} mb-1.5`}>Specialties</div>
                    <div className="flex flex-wrap gap-1.5">
                      {company.healthcare_specialties.map(s => (
                        <span key={s} className="text-[11px] px-2 py-0.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300">
                          {HEALTHCARE_SPECIALTIES.find(x => x.value === s)?.label ?? s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <Row label="Size" value={company.size ?? '—'} />
                <Row label="HQ" value={[company.headquarters_city, company.headquarters_state].filter(Boolean).join(', ') || '—'} />
                <Row label="Status" value={
                  <span className={statusBadge(company.status)}>{company.status}</span>
                } />
                <Row label="Created" value={company.created_at ? new Date(company.created_at).toLocaleDateString() : '—'} />
              </div>
            )}
          </section>

          {/* Users */}
          <section className="space-y-3">
            <div className={`${DK.label} flex items-center gap-2`}>
              <Users className="w-3 h-3" />
              Users ({company.users.length})
            </div>
            {company.users.length === 0 ? (
              <p className={`text-xs ${DK.textFaint}`}>No users linked to this company.</p>
            ) : (
              <div className="space-y-1.5">
                {company.users.map(u => (
                  <div key={u.id} className={`${DK.innerEl} px-3 py-2.5 flex items-center gap-3`}>
                    <div className="flex-1 min-w-0">
                      <div className={`text-sm font-medium ${DK.textMain} truncate`}>
                        {u.name || u.email}
                      </div>
                      <div className={`text-[11px] ${DK.textFaint} truncate`}>{u.email}</div>
                    </div>
                    <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
                      {u.job_title && <span className={`text-[10px] ${DK.textMuted}`}>{u.job_title}</span>}
                      <span className={`${DK.badge} border-zinc-700 text-zinc-400`}>{u.role}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className={`text-[11px] ${DK.textFaint} flex-shrink-0`}>{label}</span>
      <span className={`text-sm ${DK.textDim} text-right`}>{value}</span>
    </div>
  );
}

export function Companies() {
  const [companies, setCompanies] = useState<AdminCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminCompanyDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      setCompanies(await adminCompanies.list());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const openDetail = async (id: string) => {
    setSelectedId(id);
    setDetailLoading(true);
    try {
      setDetail(await adminCompanies.get(id));
    } finally {
      setDetailLoading(false);
    }
  };

  const filtered = companies.filter(c =>
    !search || c.name.toLowerCase().includes(search.toLowerCase()) ||
    (c.industry ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const industryLabel = (industry: string | null) => {
    if (!industry) return null;
    return INDUSTRY_OPTIONS.find(o => o.value === industry)?.label ?? industry;
  };

  return (
    <div className={`min-h-screen ${DK.pageBg} p-6`}>
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-zinc-400" />
            <h1 className={`text-lg font-semibold ${DK.textMain}`}>Companies</h1>
            {!loading && <span className={`text-sm ${DK.textFaint}`}>({companies.length})</span>}
          </div>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by name or industry..."
            className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-100 text-sm px-3 py-1.5 focus:outline-none focus:border-white/30 w-64 placeholder:text-zinc-600"
          />
        </div>

        {/* Table */}
        <div className={`${DK.card} overflow-hidden`}>
          {loading ? (
            <div className={`p-8 text-center text-sm ${DK.textFaint}`}>Loading...</div>
          ) : filtered.length === 0 ? (
            <div className={`p-8 text-center text-sm ${DK.textFaint}`}>No companies found.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${DK.border}`}>
                  <th className={`px-4 py-3 text-left ${DK.label}`}>Company</th>
                  <th className={`px-4 py-3 text-left ${DK.label}`}>Industry</th>
                  <th className={`px-4 py-3 text-left ${DK.label}`}>Size</th>
                  <th className={`px-4 py-3 text-left ${DK.label}`}>Status</th>
                  <th className={`px-4 py-3 text-right ${DK.label}`}>Users</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className={`divide-y ${DK.border}`}>
                {filtered.map(c => (
                  <tr
                    key={c.id}
                    className={`${DK.rowHover} cursor-pointer transition`}
                    onClick={() => openDetail(c.id)}
                  >
                    <td className="px-4 py-3">
                      <div className={`font-medium ${DK.textMain}`}>{c.name}</div>
                      {c.headquarters_city && (
                        <div className={`text-[11px] ${DK.textFaint}`}>
                          {[c.headquarters_city, c.headquarters_state].filter(Boolean).join(', ')}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className={DK.textDim}>{industryLabel(c.industry) ?? <span className={DK.textFaint}>—</span>}</div>
                      {c.industry === 'healthcare' && c.healthcare_specialties.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {c.healthcare_specialties.map(s => (
                            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-full border border-violet-500/25 text-violet-400 bg-violet-500/10">
                              {HEALTHCARE_SPECIALTIES.find(x => x.value === s)?.label ?? s}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className={`px-4 py-3 ${DK.textMuted}`}>{c.size ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={statusBadge(c.status)}>{c.status}</span>
                    </td>
                    <td className={`px-4 py-3 text-right ${DK.textMuted}`}>
                      <span className="flex items-center justify-end gap-1">
                        <Users className="w-3 h-3" />
                        {c.user_count}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ChevronRight className={`w-4 h-4 ${DK.textFaint}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Detail drawer */}
      {selectedId && (
        detailLoading ? (
          <div className="fixed inset-0 z-50 flex">
            <div className="flex-1 bg-black/50" onClick={() => setSelectedId(null)} />
            <div className={`w-[480px] h-full ${DK.pageBg} border-l ${DK.border} flex items-center justify-center`}>
              <span className={`text-sm ${DK.textFaint}`}>Loading...</span>
            </div>
          </div>
        ) : detail ? (
          <CompanyDrawer
            company={detail}
            onClose={() => { setSelectedId(null); setDetail(null); }}
            onUpdated={updated => {
              setDetail(updated);
              setCompanies(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c));
            }}
          />
        ) : null
      )}
    </div>
  );
}
