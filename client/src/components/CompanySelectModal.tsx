import { useState, useEffect } from 'react';
import type { Company } from '../types';
import { companies as companiesApi } from '../api/client';
import { Modal } from './Modal';
import { Button } from './Button';

interface CompanySelectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (companyId: string) => void;
  title?: string;
  isLoading?: boolean;
}

export function CompanySelectModal({
  isOpen,
  onClose,
  onSelect,
  title = 'Select Company',
  isLoading = false,
}: CompanySelectModalProps) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadCompanies();
    }
  }, [isOpen]);

  const loadCompanies = async () => {
    setLoading(true);
    try {
      const data = await companiesApi.list();
      setCompanies(data);
    } catch (err) {
      console.error('Failed to load companies:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredCompanies = companies.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleConfirm = () => {
    if (selectedId) {
      onSelect(selectedId);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title}>
      <div className="space-y-4">
        <p className="text-sm text-zinc-400">
          Choose a company to associate with this position:
        </p>

        <input
          type="text"
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full px-4 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-white focus:border-transparent"
        />

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
        ) : filteredCompanies.length === 0 ? (
          <div className="text-center py-8 text-zinc-500">
            {companies.length === 0 ? 'No companies found. Create a company first.' : 'No companies match your search.'}
          </div>
        ) : (
          <div className="max-h-64 overflow-y-auto space-y-1">
            {filteredCompanies.map((company) => (
              <button
                key={company.id}
                onClick={() => setSelectedId(company.id)}
                className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
                  selectedId === company.id
                    ? 'bg-matcha-500/20 border border-zinc-700 text-white'
                    : 'bg-zinc-800/50 border border-transparent hover:bg-zinc-800 text-zinc-300'
                }`}
              >
                <div className="font-medium">{company.name}</div>
                {company.industry && (
                  <div className="text-xs text-zinc-500 mt-0.5">{company.industry}</div>
                )}
              </button>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!selectedId || isLoading}
          >
            {isLoading ? (
              <>
                <svg className="w-4 h-4 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Converting...
              </>
            ) : (
              'Convert to Position'
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
