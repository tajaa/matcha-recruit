import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: Location })?.from?.pathname;

  // Get default landing page based on role
  const getDefaultRoute = (role: string) => {
    switch (role) {
      case 'candidate':
        return '/app/jobs';
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
      // Navigate based on role - use 'from' path only if user can access it
      const destination = from || getDefaultRoute(loggedInUser.role);
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-200 via-zinc-100 to-zinc-300 text-zinc-800 overflow-hidden relative font-mono selection:bg-zinc-400 selection:text-zinc-900">
      {/* Subtle grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #71717a 1px, transparent 1px),
              linear-gradient(to bottom, #71717a 1px, transparent 1px)
            `,
            backgroundSize: '40px 40px',
          }}
        />
        {/* Radial gradient overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(212,212,216,0.9)_0%,transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,rgba(161,161,170,0.7)_0%,transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(228,228,231,0.3)_100%)]" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6 border-b-2 border-zinc-400/60 bg-zinc-200/60 backdrop-blur-sm">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-zinc-700 shadow-md" />
          <span className="text-xs tracking-[0.3em] uppercase text-zinc-700 font-medium group-hover:text-zinc-900 transition-colors">
            Matcha
          </span>
        </Link>

        <Link
          to="/register"
          className="text-[10px] tracking-[0.2em] uppercase text-zinc-600 hover:text-zinc-900 transition-colors border border-zinc-400/50 hover:border-zinc-500 bg-zinc-300/30 hover:bg-zinc-300/60 px-3 py-1.5 rounded"
        >
          Register
        </Link>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-140px)] px-4">
        <div className="w-full max-w-sm">
          {/* Title */}
          <div className="text-center mb-10 p-4 bg-zinc-300/30 border border-zinc-400/40 backdrop-blur-sm rounded-sm">
            <h1 className="text-3xl font-bold tracking-[-0.02em] text-zinc-800 mb-3 drop-shadow-md">
              AUTHENTICATE
            </h1>
            <div className="h-0.5 w-20 bg-gradient-to-r from-zinc-300 via-zinc-600 to-zinc-300 mx-auto mb-3 shadow-sm" />
            <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
              Secure Access Portal
            </p>
          </div>

          {/* Form Container */}
          <div className="relative">
            {/* Corner brackets */}
            <div className="absolute -top-3 -left-3 w-8 h-8 border-t-2 border-l-2 border-zinc-500 shadow-lg" />
            <div className="absolute -top-3 -right-3 w-8 h-8 border-t-2 border-r-2 border-zinc-500 shadow-lg" />
            <div className="absolute -bottom-3 -left-3 w-8 h-8 border-b-2 border-l-2 border-zinc-500 shadow-lg" />
            <div className="absolute -bottom-3 -right-3 w-8 h-8 border-b-2 border-r-2 border-zinc-500 shadow-lg" />

            <form onSubmit={handleSubmit} className="bg-gradient-to-br from-zinc-200 via-zinc-100 to-zinc-200 border-2 border-zinc-400 p-8 shadow-xl shadow-zinc-400/50">
              {error && (
                <div className="mb-6 p-4 border-l-4 border-zinc-600 bg-zinc-300 text-zinc-800 text-[11px] tracking-wide uppercase shadow-md">
                  <span className="text-zinc-700 mr-2 font-bold">!</span>
                  {error}
                </div>
              )}

              <div className="mb-6">
                <label htmlFor="email" className="block text-[9px] tracking-[0.25em] uppercase text-zinc-700 mb-3 font-semibold">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-zinc-200 border-2 border-zinc-400 text-zinc-800 text-sm tracking-wide placeholder-zinc-500 focus:outline-none focus:border-zinc-600 focus:bg-zinc-100 transition-all shadow-md"
                  placeholder="you@example.com"
                />
              </div>

              <div className="mb-8">
                <label htmlFor="password" className="block text-[9px] tracking-[0.25em] uppercase text-zinc-700 mb-3 font-semibold">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-zinc-200 border-2 border-zinc-400 text-zinc-800 text-sm tracking-wide placeholder-zinc-500 focus:outline-none focus:border-zinc-600 focus:bg-zinc-100 transition-all shadow-md"
                  placeholder="Enter password"
                />
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3.5 bg-gradient-to-r from-zinc-600 via-zinc-700 to-zinc-600 text-zinc-100 text-[11px] tracking-[0.2em] uppercase font-bold hover:from-zinc-500 hover:via-zinc-600 hover:to-zinc-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-zinc-500/50 border-2 border-zinc-500"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-300 animate-pulse" />
                    Authenticating
                  </span>
                ) : (
                  'Initialize Session'
                )}
              </button>

              <div className="mt-6 text-center pt-6 border-t-2 border-zinc-400">
                <span className="text-[10px] tracking-wide text-zinc-600">
                  No credentials?{' '}
                  <Link to="/register" className="text-zinc-700 hover:text-zinc-900 transition-colors font-semibold underline decoration-zinc-400 hover:decoration-zinc-600">
                    Register
                  </Link>
                </span>
              </div>
            </form>
          </div>

          {/* Status indicator */}
          <div className="mt-8 flex items-center justify-center gap-3 p-4 bg-zinc-300/70 border-2 border-zinc-400 rounded backdrop-blur-sm shadow-lg">
            <div className="flex gap-1.5">
              <div className="w-2 h-2 rounded-full bg-zinc-500 animate-pulse shadow-md" />
              <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse delay-75 shadow-md" />
              <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse delay-150 shadow-md" />
            </div>
            <span className="text-[9px] tracking-[0.25em] uppercase text-zinc-700 font-bold">
              Secure Connection
            </span>
          </div>
        </div>
      </main>

      {/* Bottom line */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 border-t-2 border-zinc-400 bg-zinc-300/80 backdrop-blur-sm shadow-lg">
        <div className="flex items-center justify-center px-4 sm:px-8 py-5">
          <div className="flex items-center gap-4">
            <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 shadow-sm" />
            <div className="w-1 h-1 rounded-full bg-zinc-400 shadow-sm" />
            <span className="text-[9px] tracking-[0.25em] uppercase text-zinc-600 font-semibold">
              Matcha Recruit v1.0
            </span>
            <div className="w-1 h-1 rounded-full bg-zinc-400 shadow-sm" />
            <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 shadow-sm" />
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Login;
