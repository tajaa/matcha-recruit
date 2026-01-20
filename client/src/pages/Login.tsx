import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ParticleSphere } from '../components/ParticleSphere';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: Location })?.from?.pathname;

  const getDefaultRoute = (role: string) => {
    switch (role) {
      case 'candidate':
        return '/app/jobs';
      case 'creator':
        return '/app/gumfit';
      case 'agency':
        return '/app/gumfit/agency';
      case 'employee':
        return '/app/portal';
      case 'gumfit_admin':
        return '/app/gumfit';
      case 'admin':
      case 'client':
      default:
        return '/app';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const loggedInUser = await login({ email, password });
      const destination = from || getDefaultRoute(loggedInUser.role);
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
            <div className="w-2.5 h-2.5 rounded-full bg-zinc-900 group-hover:bg-zinc-700 transition-colors" />
            <span className="text-sm font-medium tracking-widest uppercase text-zinc-900">
              Matcha
            </span>
          </Link>

          <div className="mb-10">
            <h1 className="text-2xl font-light tracking-tight text-zinc-900 mb-2">
              Welcome back
            </h1>
            <p className="text-sm text-zinc-500">
              Please sign in to access your dashboard.
            </p>
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
                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-sm text-xs font-medium uppercase tracking-wider text-white bg-zinc-900 hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-zinc-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isLoading ? 'Signing in...' : 'Sign in'}
              </button>
            </div>

            <div className="text-center pt-4">
              <span className="text-xs text-zinc-500">
                Don't have an account?{' '}
                <Link
                  to="/register"
                  className="text-zinc-900 hover:text-zinc-700 font-medium underline underline-offset-4"
                >
                  Register
                </Link>
              </span>
            </div>
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
              Matcha Intelligence
            </footer>
          </blockquote>
        </div>
      </div>
    </div>
  );
}

export default Login;
