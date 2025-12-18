import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, Modal } from '../components';
import { companies as companiesApi } from '../api/client';
import type { Company, CompanyCreate } from '../types';

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
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight">Companies</h1>
        <Button onClick={() => setShowModal(true)}>Add Company</Button>
      </div>

      {companies.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-zinc-500 mb-4">No companies yet</p>
            <Button onClick={() => setShowModal(true)}>Add your first company</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {companies.map((company) => (
            <Card
              key={company.id}
              className="hover:border-matcha-500/50 transition-colors cursor-pointer group"
            >
              <CardContent
                className="cursor-pointer"
                onClick={() => navigate(`/companies/${company.id}`)}
              >
                <h3 className="text-xl font-semibold text-zinc-100 group-hover:text-matcha-400 transition-colors">{company.name}</h3>
                <div className="mt-2 space-y-1 text-sm text-zinc-400">
                  {company.industry && <p>Industry: <span className="text-zinc-300">{company.industry}</span></p>}
                  {company.size && <p>Size: <span className="text-zinc-300">{company.size}</span></p>}
                  <p>{company.interview_count} interview(s)</p>
                </div>
                <div className="mt-4">
                  {company.culture_profile ? (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-matcha-500/10 text-matcha-400 border border-matcha-500/20">
                      Culture Profile Ready
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
                      No Culture Profile
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Add Company">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Company Name *
            </label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 placeholder-zinc-600 outline-none transition-all"
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Industry</label>
            <input
              type="text"
              value={formData.industry}
              onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 placeholder-zinc-600 outline-none transition-all"
              placeholder="Technology"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Size</label>
            <select
              value={formData.size}
              onChange={(e) => setFormData({ ...formData, size: e.target.value })}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 outline-none transition-all"
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
