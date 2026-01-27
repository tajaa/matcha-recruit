import { useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

type RegistrationType = 'candidate' | 'business';

const INDUSTRY_OPTIONS = [
  'Technology',
  'Healthcare',
  'Finance',
  'Retail',
  'Manufacturing',
  'Education',
  'Professional Services',
  'Real Estate',
  'Hospitality',
  'Other',
];

const COMPANY_SIZE_OPTIONS = [
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-500', label: '201-500 employees' },
  { value: '500+', label: '500+ employees' },
];

export function Register() {
  const [type, setType] = useState<RegistrationType>('candidate');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('');
  const [companySize, setCompanySize] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { registerBusiness, registerCandidate } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get('returnTo');

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
        // Candidates go through resume onboarding
        const destination = returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : '';
        navigate(`/onboarding/resume${destination}`);
      } else {
        if (!companyName.trim()) {
          setError('Please enter your company name');
          setIsLoading(false);
          return;
        }
        await registerBusiness({
          company_name: companyName,
          industry: industry || undefined,
          company_size: companySize || undefined,
          email,
          password,
          name,
          phone: phone || undefined,
          job_title: jobTitle || undefined,
        });
        // Business users go to app
        navigate(returnTo || '/app');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  const inputClasses =
    'appearance-none block w-full px-3 py-2 border border-zinc-200 rounded-sm shadow-sm placeholder-zinc-400 focus:outline-none focus:border-zinc-400 focus:ring-0 sm:text-sm transition-colors';

  return (
    <div className="min-h-screen bg-zinc-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link to="/" className="flex items-center justify-center gap-2 mb-6">
          <div className="w-2 h-2 rounded-full bg-zinc-900" />
          <span className="text-sm font-medium tracking-widest uppercase text-zinc-900">
            Matcha
          </span>
        </Link>
        <h2 className="mt-2 text-center text-xl font-light tracking-tight text-zinc-900">
          Create your account
        </h2>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-[420px]">
        <div className="bg-white py-8 px-4 border border-zinc-200 shadow-sm sm:rounded-sm sm:px-10">
          <div className="flex border-b border-zinc-100 mb-6">
            <button
              type="button"
              onClick={() => setType('candidate')}
              className={`flex-1 pb-3 text-xs font-medium uppercase tracking-wider text-center transition-colors border-b-2 ${
                type === 'candidate'
                  ? 'border-zinc-900 text-zinc-900'
                  : 'border-transparent text-zinc-400 hover:text-zinc-600'
              }`}
            >
              Candidate
            </button>
            <button
              type="button"
              onClick={() => setType('business')}
              className={`flex-1 pb-3 text-xs font-medium uppercase tracking-wider text-center transition-colors border-b-2 ${
                type === 'business'
                  ? 'border-zinc-900 text-zinc-900'
                  : 'border-transparent text-zinc-400 hover:text-zinc-600'
              }`}
            >
              Business
            </button>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="text-xs text-red-600 bg-red-50 border border-red-100 p-2 rounded-sm text-center">
                {error}
              </div>
            )}

            <div>
              <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                Full Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className={inputClasses}
                placeholder="John Doe"
              />
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
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

            <div>
              <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                Phone <span className="text-zinc-400 font-normal normal-case ml-1">(Optional)</span>
              </label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className={inputClasses}
                placeholder="+1 (555) 123-4567"
              />
            </div>

            {type === 'business' && (
              <>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    required
                    className={inputClasses}
                    placeholder="Acme Corp"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                      Industry <span className="text-zinc-400 font-normal normal-case ml-1">(Optional)</span>
                    </label>
                    <select
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      className={`${inputClasses} cursor-pointer`}
                    >
                      <option value="">Select industry</option>
                      {INDUSTRY_OPTIONS.map((ind) => (
                        <option key={ind} value={ind}>
                          {ind}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                      Company Size <span className="text-zinc-400 font-normal normal-case ml-1">(Optional)</span>
                    </label>
                    <select
                      value={companySize}
                      onChange={(e) => setCompanySize(e.target.value)}
                      className={`${inputClasses} cursor-pointer`}
                    >
                      <option value="">Select size</option>
                      {COMPANY_SIZE_OPTIONS.map((size) => (
                        <option key={size.value} value={size.value}>
                          {size.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                    Job Title <span className="text-zinc-400 font-normal normal-case ml-1">(Optional)</span>
                  </label>
                  <input
                    type="text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    className={inputClasses}
                    placeholder="HR Manager"
                  />
                </div>
              </>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className={inputClasses}
                  placeholder="Min 8 chars"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                  Confirm
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className={inputClasses}
                  placeholder="Repeat"
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-sm shadow-sm text-xs font-medium uppercase tracking-wider text-white bg-zinc-900 hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-zinc-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isLoading ? 'Creating Account...' : 'Create Account'}
              </button>
            </div>
          </form>

          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-zinc-200" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-zinc-400 text-[10px] uppercase tracking-wider">
                  Already registered?
                </span>
              </div>
            </div>

            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="text-xs font-medium text-zinc-900 hover:text-zinc-700 hover:underline underline-offset-4"
              >
                Sign in
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Register;
