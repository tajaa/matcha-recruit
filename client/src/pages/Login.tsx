import { useEffect, useState } from 'react';
import { useNavigate, useLocation, Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ParticleSphere } from '../components/ParticleSphere';
import { auth } from '../api/client';
import type { BrokerBrandingRuntime } from '../types';
import { getAppHomePath } from '../utils/homeRoute';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [branding, setBranding] = useState<BrokerBrandingRuntime | null>(null);
  const [brandingError, setBrandingError] = useState('');
  const [brandingLoading, setBrandingLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { brokerSlug } = useParams<{ brokerSlug: string }>();

  const brokerFromQuery = new URLSearchParams(location.search).get('broker') || '';
  const brokerKey = (brokerSlug || brokerFromQuery).trim().toLowerCase();

  const from = (location.state as {
    from?: { pathname?: string; search?: string; hash?: string };
  })?.from;

  useEffect(() => {
    let cancelled = false;

    if (!brokerKey) {
      setBranding(null);
      setBrandingError('');
      setBrandingLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setBrandingLoading(true);
    setBrandingError('');
    auth
      .getBrokerBranding(brokerKey)
      .then((result) => {
        if (!cancelled) {
          setBranding(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setBranding(null);
          setBrandingError(err instanceof Error ? err.message : 'Unable to load broker branding');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBrandingLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [brokerKey]);

  const brandName = branding?.brand_display_name || 'Matcha';
  const primaryColor = branding?.primary_color || '#18181b';
  const showPoweredBy = !branding || branding.powered_by_badge || !branding.hide_matcha_identity;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const loggedInUser = await login({ email, password });
      const destination = from?.pathname
        ? `${from.pathname}${from.search || ''}${from.hash || ''}`
        : getAppHomePath(loggedInUser.role);
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex font-sans bg-white">
      {/* Left Column - Form */}
      <div className="w-full lg:w-[480px] xl:w-[560px] flex flex-col justify-center px-8 sm:px-12 lg:px-16 xl:px-20 border-r border-zinc-100 z-10 bg-white">
        <div className="w-full max-w-sm mx-auto">
          <Link to="/" className="inline-flex items-center gap-2 mb-12 group">
            {branding?.logo_url ? (
              <img src={branding.logo_url} alt={`${brandName} logo`} className="h-6 w-6 rounded-sm object-cover" />
            ) : (
              <div className="w-2.5 h-2.5 rounded-full transition-colors" style={{ backgroundColor: primaryColor }} />
            )}
            <span className="text-sm font-medium tracking-widest uppercase text-zinc-900">
              {brandName}
            </span>
          </Link>

          <div className="mb-10">
            <h1 className="text-2xl font-light tracking-tight text-zinc-900 mb-2">
              Welcome back
            </h1>
            <p className="text-sm text-zinc-500">
              Please sign in to access your dashboard{branding ? ` for ${brandName}` : ''}.
            </p>
            {brandingLoading && (
              <p className="text-xs text-zinc-400 mt-2">Loading broker branding...</p>
            )}
            {brandingError && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-sm px-2 py-1 mt-2">
                {brandingError}. Using default Matcha login.
              </p>
            )}
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="text-xs text-red-600 bg-red-50 border border-red-100 p-3 rounded-sm">
                {error}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full px-0 py-2 border-b border-zinc-200 bg-transparent text-sm text-zinc-900 placeholder-zinc-300 focus:border-zinc-900 focus:ring-0 transition-colors"
                  placeholder="name@company.com"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-1.5">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full px-0 py-2 border-b border-zinc-200 bg-transparent text-sm text-zinc-900 placeholder-zinc-300 focus:border-zinc-900 focus:ring-0 transition-colors"
                  placeholder="••••••••"
                />
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-sm text-xs font-medium uppercase tracking-wider text-white focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                style={{ backgroundColor: primaryColor, boxShadow: 'none' }}
              >
                {isLoading ? 'Signing in...' : 'Sign in'}
              </button>
            </div>

            <div className="text-center pt-4">
              <span className="text-xs text-zinc-500">
                Don't have an account?{' '}
                <Link
                  to={brokerKey ? `/register?broker=${encodeURIComponent(brokerKey)}` : '/register'}
                  className="font-medium underline underline-offset-4"
                  style={{ color: primaryColor }}
                >
                  Register
                </Link>
              </span>
            </div>
            {showPoweredBy && (
              <p className="text-[10px] uppercase tracking-wider text-zinc-400 text-center">Powered by Matcha</p>
            )}
            {branding?.support_email && (
              <p className="text-xs text-zinc-500 text-center">
                Need help? Contact{' '}
                <a className="underline" href={`mailto:${branding.support_email}`}>
                  {branding.support_email}
                </a>
              </p>
            )}
          </form>
        </div>
      </div>

      {/* Right Column - Visual */}
      <div className="hidden lg:block flex-1 bg-zinc-900 relative overflow-hidden">
        {/* Abstract Pattern overlay */}
        <div 
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)`,
            backgroundSize: '40px 40px'
          }}
        />
        
        {/* Hero Visual */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-full h-full max-w-2xl max-h-[800px] relative">
             <ParticleSphere className="w-full h-full" />
          </div>
        </div>

        {/* Caption */}
        <div className="absolute bottom-12 left-12 right-12 z-10">
          <blockquote className="text-white max-w-md">
            <p className="text-lg font-light leading-relaxed mb-4">
              "The future of recruiting is intelligent, data-driven, and seamlessly connected."
            </p>
            <footer className="text-sm text-zinc-500 font-mono uppercase tracking-widest">
              {brandName}
            </footer>
          </blockquote>
        </div>
      </div>
    </div>
  );
}

export default Login;
