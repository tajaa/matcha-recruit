import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useChatAuth } from '../../context/ChatAuthContext';
import { MessageCircle } from 'lucide-react';

export function ChatRegister() {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useChatAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    setIsLoading(true);

    try {
      await register({
        email,
        first_name: firstName,
        last_name: lastName,
        password,
      });
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="p-3 bg-white/5 border border-white/10 rounded-sm">
              <MessageCircle className="w-6 h-6 text-emerald-400" />
            </div>
          </div>
          <h1 className="text-3xl font-bold tracking-tighter text-white uppercase mb-2">
            Join the Community
          </h1>
          <p className="text-sm text-zinc-500">
            Create your account to start chatting
          </p>
        </div>

        {/* Form */}
        <div className="border border-white/10 bg-zinc-900/50 p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="text-xs text-red-400 bg-red-950/50 border border-red-900/50 p-3 rounded-sm">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="firstName" className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                  First Name
                </label>
                <input
                  id="firstName"
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="block w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors"
                  placeholder="Jane"
                />
              </div>

              <div>
                <label htmlFor="lastName" className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                  Last Name
                </label>
                <input
                  id="lastName"
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="block w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors"
                  placeholder="Doe"
                />
              </div>
            </div>

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
                placeholder="jane@example.com"
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

            <div>
              <label htmlFor="confirmPassword" className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="block w-full px-4 py-3 bg-zinc-950 border border-white/10 text-sm text-white placeholder-zinc-600 focus:border-white/30 focus:ring-0 focus:outline-none transition-colors"
                placeholder="••••••••"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 bg-white text-black text-xs font-mono uppercase tracking-widest font-bold hover:bg-zinc-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-950 focus:ring-white disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isLoading ? 'Creating account...' : 'Create Account'}
              </button>
            </div>

            <div className="text-center pt-4">
              <span className="text-xs text-zinc-500">
                Already have an account?{' '}
                <Link
                  to="/chat/login"
                  className="text-white hover:text-zinc-300 font-medium underline underline-offset-4"
                >
                  Sign in
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

export default ChatRegister;
