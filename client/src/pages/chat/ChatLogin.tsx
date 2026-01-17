import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useChatAuth } from '../../context/ChatAuthContext';
import { MessageCircle } from 'lucide-react';

export function ChatLogin() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useChatAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="p-3 bg-white/5 border border-white/10 rounded-sm">
              <MessageCircle className="w-6 h-6 text-emerald-400" />
            </div>
          </div>
          <h1 className="text-3xl font-bold tracking-tighter text-white uppercase mb-2">
            Community Chat
          </h1>
          <p className="text-sm text-zinc-500">
            Connect with the job hunting community
          </p>
        </div>

        {/* Form */}
        <div className="border border-white/10 bg-zinc-900/50 p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="text-xs text-red-400 bg-red-950/50 border border-red-900/50 p-3 rounded-sm">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-4 bg-white text-black text-xs font-mono uppercase tracking-widest font-bold hover:bg-zinc-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-950 focus:ring-white disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isLoading ? 'Signing in...' : 'Sign in'}
            </button>

            <div className="text-center pt-4">
              <span className="text-xs text-zinc-500">
                Don't have an account?{' '}
                <Link
                  to="/chat/register"
                  className="text-white hover:text-zinc-300 font-medium underline underline-offset-4"
                >
                  Create one
                </Link>
              </span>
            </div>
          </form>
        </div>

        {/* Back to main app */}
        <div className="text-center mt-6">
          <Link
            to="/"
            className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            Back to Matcha
          </Link>
        </div>
      </div>
    </div>
  );
}

export default ChatLogin;
