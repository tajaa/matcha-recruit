import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, Modal } from '../components';
import { companies as companiesApi } from '../api/client';
import type { Company, CompanyCreate } from '../types';

const inputClasses =
  'w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 focus:shadow-[0_0_10px_rgba(34,197,94,0.1)] transition-all font-mono';

export function Companies() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState<CompanyCreate>({ name: '', industry: '', size: '' });

  const fetchCompanies = async () => {
    try {
      const data = await companiesApi.list();
      setCompanies(data);
    } catch (err) {
      console.error('Failed to fetch companies:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCompanies();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await companiesApi.create(formData);
      setShowModal(false);
      setFormData({ name: '', industry: '', size: '' });
      fetchCompanies();
    } catch (err) {
      console.error('Failed to create company:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          <span className="text-[11px] tracking-[0.2em] uppercase text-zinc-500">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="pb-12">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-[-0.02em] text-white mb-1">COMPANIES</h1>
          <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
            Organization Management
          </p>
        </div>
        <Button onClick={() => setShowModal(true)}>Add Company</Button>
      </div>

      {companies.length === 0 ? (
        <Card>
          <CardContent className="text-center py-16">
            <div className="w-12 h-12 mx-auto mb-4 border border-zinc-800 flex items-center justify-center">
              <span className="text-zinc-600 text-2xl">+</span>
            </div>
            <p className="text-[11px] tracking-[0.15em] uppercase text-zinc-500 mb-6">
              No companies registered
            </p>
            <Button onClick={() => setShowModal(true)}>Initialize First Company</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {companies.map((company) => (
            <Card
              key={company.id}
              className="cursor-pointer group"
            >
              <CardContent
                className="cursor-pointer"
                onClick={() => navigate(`/app/companies/${company.id}`)}
              >
                <div className="flex items-start justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white group-hover:text-matcha-400 transition-colors tracking-tight">
                    {company.name}
                  </h3>
                  <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
                </div>

                <div className="space-y-2 text-[11px] tracking-wide">
                  {company.industry && (
                    <div className="flex justify-between">
                      <span className="text-zinc-600 uppercase">Industry</span>
                      <span className="text-zinc-300">{company.industry}</span>
                    </div>
                  )}
                  {company.size && (
                    <div className="flex justify-between">
                      <span className="text-zinc-600 uppercase">Size</span>
                      <span className="text-zinc-300 capitalize">{company.size}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-zinc-600 uppercase">Interviews</span>
                    <span className="text-zinc-300">{company.interview_count}</span>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-zinc-800">
                  {company.culture_profile ? (
                    <div className="flex items-center gap-2">
                      <div className="w-1 h-1 rounded-full bg-matcha-500" />
                      <span className="text-[9px] tracking-[0.15em] uppercase text-matcha-500">
                        Culture Profile Active
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <div className="w-1 h-1 rounded-full bg-zinc-600" />
                      <span className="text-[9px] tracking-[0.15em] uppercase text-zinc-600">
                        No Culture Profile
                      </span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Add Company">
        <form onSubmit={handleCreate} className="space-y-5">
          <div>
            <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
              Company Name <span className="text-matcha-500">*</span>
            </label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className={inputClasses}
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
              Industry
            </label>
            <input
              type="text"
              value={formData.industry}
              onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
              className={inputClasses}
              placeholder="Technology"
            />
          </div>
          <div>
            <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
              Size
            </label>
            <select
              value={formData.size}
              onChange={(e) => setFormData({ ...formData, size: e.target.value })}
              className={`${inputClasses} appearance-none cursor-pointer`}
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat',
                backgroundPosition: 'right 12px center',
                backgroundSize: '16px',
              }}
            >
              <option value="">Select size</option>
              <option value="startup">Startup (1-50)</option>
              <option value="mid">Mid-size (50-500)</option>
              <option value="enterprise">Enterprise (500+)</option>
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800 mt-6">
            <Button type="button" variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button type="submit">Create</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Companies;
