import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { companies } from '../api/client';
import { Button } from '../components';
import type { Company } from '../types';

type RegistrationType = 'candidate' | 'client';

export function Register() {
  const [type, setType] = useState<RegistrationType>('candidate');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [companyId, setCompanyId] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [companiesList, setCompaniesList] = useState<Company[]>([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { registerClient, registerCandidate } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (type === 'client') {
      companies.list().then(setCompaniesList).catch(console.error);
    }
  }, [type]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);

    try {
      if (type === 'candidate') {
        await registerCandidate({ email, password, name, phone: phone || undefined });
      } else {
        if (!companyId) {
          setError('Please select a company');
          setIsLoading(false);
          return;
        }
        await registerClient({
          email,
          password,
          name,
          company_id: companyId,
          phone: phone || undefined,
          job_title: jobTitle || undefined,
        });
      }
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-lg bg-matcha-500 flex items-center justify-center text-zinc-950 font-bold text-2xl mx-auto mb-4">
            M
          </div>
          <h1 className="text-2xl font-bold text-white">Create an account</h1>
        </div>

        <div className="bg-zinc-900 rounded-xl p-6 border border-white/5">
          {/* Registration type toggle */}
          <div className="flex gap-2 mb-6">
            <button
              type="button"
              onClick={() => setType('candidate')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                type === 'candidate'
                  ? 'bg-matcha-500 text-zinc-950'
                  : 'bg-zinc-800 text-zinc-400 hover:text-white'
              }`}
            >
              Candidate
            </button>
            <button
              type="button"
              onClick={() => setType('client')}
              className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                type === 'client'
                  ? 'bg-matcha-500 text-zinc-950'
                  : 'bg-zinc-800 text-zinc-400 hover:text-white'
              }`}
            >
              Company Client
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {error && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                {error}
              </div>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-400 mb-2">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                placeholder="Your full name"
              />
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-400 mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                placeholder="you@example.com"
              />
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-400 mb-2">Phone (optional)</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                placeholder="+1 (555) 123-4567"
              />
            </div>

            {type === 'client' && (
              <>
                <div className="mb-4">
                  <label className="block text-sm font-medium text-zinc-400 mb-2">Company</label>
                  <select
                    value={companyId}
                    onChange={(e) => setCompanyId(e.target.value)}
                    required
                    className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-matcha-500"
                  >
                    <option value="">Select a company</option>
                    {companiesList.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-zinc-400 mb-2">Job Title (optional)</label>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                    placeholder="Hiring Manager"
                  />
                </div>
              </>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-400 mb-2">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                placeholder="At least 8 characters"
              />
            </div>

            <div className="mb-6">
              <label className="block text-sm font-medium text-zinc-400 mb-2">Confirm Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
                placeholder="Confirm your password"
              />
            </div>

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Creating account...' : 'Create account'}
            </Button>

            <div className="mt-4 text-center text-sm text-zinc-400">
              Already have an account?{' '}
              <Link to="/login" className="text-matcha-400 hover:text-matcha-300">
                Sign in
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
