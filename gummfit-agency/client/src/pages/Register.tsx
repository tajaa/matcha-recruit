import { useState } from 'react';
import { useNavigate, Link, useParams } from 'react-router-dom';
import { Eye, EyeOff, UserPlus, Loader2, Building2, User } from 'lucide-react';
import { api } from '../api/client';

export function Register() {
  const { type } = useParams<{ type: string }>();
  const isAgency = type === 'agency';
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    // Creator fields
    display_name: '',
    // Agency fields
    agency_name: '',
    agency_type: 'talent' as string,
    website_url: '',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isAgency) {
        await api.auth.registerAgency({
          email: formData.email,
          password: formData.password,
          agency_name: formData.agency_name,
          agency_type: formData.agency_type,
          website_url: formData.website_url || undefined,
        });
      } else {
        await api.auth.registerCreator({
          email: formData.email,
          password: formData.password,
          display_name: formData.display_name,
        });
      }

      navigate('/login');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/gumfit-landing" className="inline-block">
            <h1 className="text-3xl font-bold text-matcha-500">GumFit</h1>
          </Link>
          <p className="mt-2 text-zinc-400">
            {isAgency ? 'Register your agency' : 'Create your creator account'}
          </p>
        </div>

        {/* Role toggle */}
        <div className="flex gap-2 mb-6">
          <Link
            to="/register/creator"
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              !isAgency
                ? 'bg-matcha-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-300'
            }`}
          >
            <User className="w-4 h-4" />
            Creator
          </Link>
          <Link
            to="/register/agency"
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              isAgency
                ? 'bg-matcha-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:text-zinc-300'
            }`}
          >
            <Building2 className="w-4 h-4" />
            Agency
          </Link>
        </div>

        <form onSubmit={handleRegister} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-zinc-300 mb-1">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
              placeholder="you@example.com"
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-zinc-300 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                value={formData.password}
                onChange={handleChange}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 pr-10 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
                placeholder="Create a password"
                required
                minLength={8}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-300"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {!isAgency && (
            <div>
              <label htmlFor="display_name" className="block text-sm font-medium text-zinc-300 mb-1">
                Display Name
              </label>
              <input
                id="display_name"
                name="display_name"
                type="text"
                value={formData.display_name}
                onChange={handleChange}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
                placeholder="Your creator name"
                required
              />
            </div>
          )}

          {isAgency && (
            <>
              <div>
                <label htmlFor="agency_name" className="block text-sm font-medium text-zinc-300 mb-1">
                  Agency Name
                </label>
                <input
                  id="agency_name"
                  name="agency_name"
                  type="text"
                  value={formData.agency_name}
                  onChange={handleChange}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
                  placeholder="Your agency name"
                  required
                />
              </div>
              <div>
                <label htmlFor="agency_type" className="block text-sm font-medium text-zinc-300 mb-1">
                  Agency Type
                </label>
                <select
                  id="agency_type"
                  name="agency_type"
                  value={formData.agency_type}
                  onChange={handleChange}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
                  required
                >
                  <option value="talent">Talent Management</option>
                  <option value="marketing">Marketing</option>
                  <option value="sports">Sports</option>
                  <option value="modeling">Modeling</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label htmlFor="website_url" className="block text-sm font-medium text-zinc-300 mb-1">
                  Website <span className="text-zinc-500">(optional)</span>
                </label>
                <input
                  id="website_url"
                  name="website_url"
                  type="url"
                  value={formData.website_url}
                  onChange={handleChange}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500 focus:border-transparent"
                  placeholder="https://agency.com"
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="mt-6 text-center text-zinc-400 text-sm">
          Already have an account?{' '}
          <Link to="/login" className="text-matcha-500 hover:text-matcha-400">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
