import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { companies } from '../api/client';
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
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get('returnTo');

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
      // Redirect to returnTo URL if provided, otherwise go to app
      navigate(returnTo || '/app');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  const inputClasses =
    'w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 focus:shadow-[0_0_10px_rgba(34,197,94,0.1)] transition-all';

  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Subtle grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        {/* Radial vignette */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#09090b_70%)]" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.8)]" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium group-hover:text-matcha-400 transition-colors">
            Matcha
          </span>
        </Link>

        <Link
          to="/login"
          className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
        >
          Login
        </Link>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-140px)] px-4 py-8">
        <div className="w-full max-w-md">
          {/* Title */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold tracking-[-0.02em] text-white mb-2">INITIALIZE</h1>
            <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
              Create New Profile
            </p>
          </div>

          {/* Form Container */}
          <div className="relative">
            {/* Corner brackets */}
            <div className="absolute -top-3 -left-3 w-6 h-6 border-t border-l border-zinc-700" />
            <div className="absolute -top-3 -right-3 w-6 h-6 border-t border-r border-zinc-700" />
            <div className="absolute -bottom-3 -left-3 w-6 h-6 border-b border-l border-zinc-700" />
            <div className="absolute -bottom-3 -right-3 w-6 h-6 border-b border-r border-zinc-700" />

            <div className="bg-zinc-900/50 border border-zinc-800 p-8">
              {/* Registration type toggle */}
              <div className="flex gap-2 mb-8">
                <button
                  type="button"
                  onClick={() => setType('candidate')}
                  className={`flex-1 py-2.5 text-[10px] tracking-[0.15em] uppercase font-medium transition-all ${
                    type === 'candidate'
                      ? 'bg-matcha-500 text-black'
                      : 'bg-zinc-950 border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700'
                  }`}
                >
                  Candidate
                </button>
                <button
                  type="button"
                  onClick={() => setType('client')}
                  className={`flex-1 py-2.5 text-[10px] tracking-[0.15em] uppercase font-medium transition-all ${
                    type === 'client'
                      ? 'bg-matcha-500 text-black'
                      : 'bg-zinc-950 border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700'
                  }`}
                >
                  Company Client
                </button>
              </div>

              <form onSubmit={handleSubmit}>
                {error && (
                  <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide uppercase">
                    <span className="text-red-500 mr-2">!</span>
                    {error}
                  </div>
                )}

                <div className="mb-5">
                  <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    className={inputClasses}
                    placeholder="Your full name"
                  />
                </div>

                <div className="mb-5">
                  <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className={inputClasses}
                    placeholder="you@example.com"
                  />
                </div>

                <div className="mb-5">
                  <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Phone{' '}
                    <span className="text-zinc-700">(Optional)</span>
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className={inputClasses}
                    placeholder="+1 (555) 123-4567"
                  />
                </div>

                {type === 'client' && (
                  <>
                    <div className="mb-5">
                      <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                        Company
                      </label>
                      <select
                        value={companyId}
                        onChange={(e) => setCompanyId(e.target.value)}
                        required
                        className={`${inputClasses} appearance-none cursor-pointer`}
                        style={{
                          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
                          backgroundRepeat: 'no-repeat',
                          backgroundPosition: 'right 12px center',
                          backgroundSize: '16px',
                        }}
                      >
                        <option value="">Select a company</option>
                        {companiesList.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="mb-5">
                      <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                        Job Title{' '}
                        <span className="text-zinc-700">(Optional)</span>
                      </label>
                      <input
                        type="text"
                        value={jobTitle}
                        onChange={(e) => setJobTitle(e.target.value)}
                        className={inputClasses}
                        placeholder="Hiring Manager"
                      />
                    </div>
                  </>
                )}

                <div className="mb-5">
                  <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className={inputClasses}
                    placeholder="Min 8 characters"
                  />
                </div>

                <div className="mb-8">
                  <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                    Confirm Password
                  </label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className={inputClasses}
                    placeholder="Confirm password"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-[0_0_20px_rgba(34,197,94,0.3)]"
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-black/50 animate-pulse" />
                      Creating Profile
                    </span>
                  ) : (
                    'Create Profile'
                  )}
                </button>

                <div className="mt-6 text-center">
                  <span className="text-[10px] tracking-wide text-zinc-600">
                    Already registered?{' '}
                    <Link to="/login" className="text-matcha-500 hover:text-matcha-400 transition-colors">
                      Login
                    </Link>
                  </span>
                </div>
              </form>
            </div>
          </div>

          {/* Status indicator */}
          <div className="mt-8 flex items-center justify-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">
              Secure Connection
            </span>
          </div>
        </div>
      </main>

      {/* Bottom line */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 border-t border-zinc-800/50">
        <div className="flex items-center justify-center px-4 sm:px-8 py-4">
          <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-700">
            Matcha Recruit v1.0
          </span>
        </div>
      </footer>
    </div>
  );
}
