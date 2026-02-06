import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Clock, Mail } from 'lucide-react';

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
  const [registrationPending, setRegistrationPending] = useState(false);

  const { registerBusiness } = useAuth();

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

    if (!companyName.trim()) {
      setError('Please enter your company name');
      return;
    }

    setIsLoading(true);

    try {
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
      setRegistrationPending(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  const inputClasses =
    'appearance-none block w-full px-3 py-2 border border-zinc-200 rounded-sm shadow-sm text-zinc-900 placeholder-zinc-500 focus:outline-none focus:border-zinc-400 focus:ring-0 sm:text-sm transition-colors';

  // Show pending approval screen after successful business registration
  if (registrationPending) {
    return (
      <div className="min-h-screen bg-zinc-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link to="/" className="flex items-center justify-center gap-2 mb-6">
            <div className="w-2 h-2 rounded-full bg-zinc-900" />
            <span className="text-sm font-medium tracking-widest uppercase text-zinc-900">
              Matcha
            </span>
          </Link>
        </div>

        <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-[420px]">
          <div className="bg-white py-8 px-4 border border-zinc-200 shadow-sm sm:rounded-sm sm:px-10">
            <div className="text-center mb-6">
              <div className="w-12 h-12 mx-auto mb-4 bg-amber-50 border border-amber-200 rounded-full flex items-center justify-center">
                <Clock size={24} className="text-amber-600" />
              </div>
              <h2 className="text-xl font-medium text-zinc-900 mb-2">Registration Pending</h2>
              <p className="text-sm text-zinc-600">{companyName}</p>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-sm p-4 mb-6">
              <div className="flex items-center gap-2 text-amber-700 text-xs font-medium uppercase tracking-wider mb-2">
                <span className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
                Under Review
              </div>
              <p className="text-zinc-700 text-sm leading-relaxed">
                Your business registration has been submitted and is awaiting approval. You'll receive an email once it's reviewed.
              </p>
            </div>

            <div className="space-y-3 text-sm text-zinc-600 mb-6">
              <div className="flex items-start gap-3">
                <div className="w-5 h-5 bg-zinc-100 border border-zinc-200 rounded-full flex items-center justify-center text-xs text-zinc-500 font-medium shrink-0 mt-0.5">1</div>
                <p>Our team reviews your registration within 1-2 business days</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-5 h-5 bg-zinc-100 border border-zinc-200 rounded-full flex items-center justify-center text-xs text-zinc-500 font-medium shrink-0 mt-0.5">2</div>
                <p>You'll receive an email when your account is approved</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-5 h-5 bg-zinc-100 border border-zinc-200 rounded-full flex items-center justify-center text-xs text-zinc-500 font-medium shrink-0 mt-0.5">3</div>
                <p>Once approved, log in to access all Matcha features</p>
              </div>
            </div>

            <div className="bg-zinc-50 border border-zinc-200 rounded-sm p-3 mb-6">
              <div className="flex items-center gap-2 text-zinc-600 text-xs">
                <Mail size={14} />
                <span>Questions? Contact us at </span>
                <a href="mailto:support@hey-matcha.com" className="text-zinc-900 font-medium hover:underline">
                  support@hey-matcha.com
                </a>
              </div>
            </div>

            <Link
              to="/login"
              className="w-full flex justify-center py-2.5 px-4 border border-zinc-200 rounded-sm text-xs font-medium uppercase tracking-wider text-zinc-700 bg-white hover:bg-zinc-50 transition-colors"
            >
              Go to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

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
          Create your business account
        </h2>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-[420px]">
        <div className="bg-white py-8 px-4 border border-zinc-200 shadow-sm sm:rounded-sm sm:px-10">
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
