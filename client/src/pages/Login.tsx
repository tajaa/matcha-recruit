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

  const from = (location.state as { from?: Location })?.from?.pathname || '/app';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

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
          to="/register"
          className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
        >
          Register
        </Link>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-140px)] px-4">
        <div className="w-full max-w-sm">
          {/* Title */}
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold tracking-[-0.02em] text-white mb-2">
              AUTHENTICATE
            </h1>
            <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
              Secure Access Portal
            </p>
          </div>

          {/* Form Container */}
          <div className="relative">
            {/* Corner brackets */}
            <div className="absolute -top-3 -left-3 w-6 h-6 border-t border-l border-zinc-700" />
            <div className="absolute -top-3 -right-3 w-6 h-6 border-t border-r border-zinc-700" />
            <div className="absolute -bottom-3 -left-3 w-6 h-6 border-b border-l border-zinc-700" />
            <div className="absolute -bottom-3 -right-3 w-6 h-6 border-b border-r border-zinc-700" />

            <form onSubmit={handleSubmit} className="bg-zinc-900/50 border border-zinc-800 p-8">
              {error && (
                <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide uppercase">
                  <span className="text-red-500 mr-2">!</span>
                  {error}
                </div>
              )}

              <div className="mb-6">
                <label htmlFor="email" className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 focus:shadow-[0_0_10px_rgba(34,197,94,0.1)] transition-all"
                  placeholder="you@example.com"
                />
              </div>

              <div className="mb-8">
                <label htmlFor="password" className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 focus:shadow-[0_0_10px_rgba(34,197,94,0.1)] transition-all"
                  placeholder="Enter password"
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
                    Authenticating
                  </span>
                ) : (
                  'Initialize Session'
                )}
              </button>

              <div className="mt-6 text-center">
                <span className="text-[10px] tracking-wide text-zinc-600">
                  No credentials?{' '}
                  <Link to="/register" className="text-matcha-500 hover:text-matcha-400 transition-colors">
                    Register
                  </Link>
                </span>
              </div>
            </form>
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

export default Login;
