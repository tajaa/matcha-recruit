import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';

interface NavItem {
  path: string;
  label: string;
  roles: UserRole[];
}

const allNavItems: NavItem[] = [
  { path: '/app', label: 'Companies', roles: ['admin', 'client'] },
  { path: '/app/positions', label: 'Positions', roles: ['admin', 'client', 'candidate'] },
  { path: '/app/candidates', label: 'Candidates', roles: ['admin', 'client'] },
  { path: '/app/jobs', label: 'Job Search', roles: ['admin', 'candidate'] },
  { path: '/app/test-bot', label: 'Test Bot', roles: ['admin', 'candidate'] },
  { path: '/app/import', label: 'Import', roles: ['admin'] },
  { path: '/careers', label: 'Careers', roles: ['admin', 'client', 'candidate'] },
];

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout, hasRole } = useAuth();

  // Filter nav items based on user role
  const navItems = allNavItems.filter((item) => hasRole(...item.roles));

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-mono selection:bg-matcha-500 selection:text-black">
      {/* Subtle grid background */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
      </div>

      <nav className="fixed top-0 inset-x-0 z-50 bg-zinc-950/90 backdrop-blur-sm border-b border-zinc-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-14">
            <div className="flex items-center gap-8">
              <Link to="/" className="flex-shrink-0 flex items-center gap-2 group">
                <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
                <span className="text-xs tracking-[0.25em] uppercase text-matcha-500 font-medium group-hover:text-matcha-400 transition-colors">
                  Matcha
                </span>
              </Link>
              <div className="hidden sm:flex sm:items-center sm:gap-1">
                {navItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`px-3 py-1.5 text-[10px] tracking-[0.15em] uppercase transition-all ${
                      location.pathname === item.path
                        ? 'text-matcha-400 bg-matcha-500/10 border border-matcha-500/20'
                        : 'text-zinc-500 hover:text-zinc-300 border border-transparent hover:border-zinc-800'
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>

            {/* User menu */}
            {user && (
              <div className="flex items-center gap-4">
                <div className="hidden md:flex items-center gap-3 text-[10px]">
                  <span className="text-zinc-600 tracking-wide">OPERATOR:</span>
                  <span className="text-zinc-300 tracking-wide">{user.email}</span>
                  <span className="px-2 py-0.5 bg-matcha-500/10 text-matcha-500 border border-matcha-500/20 tracking-[0.15em] uppercase">
                    {user.role}
                  </span>
                </div>
                <Link
                  to="/app/settings"
                  className={`p-2 transition-colors ${
                    location.pathname === '/app/settings'
                      ? 'text-matcha-400'
                      : 'text-zinc-600 hover:text-zinc-300'
                  }`}
                  title="Settings"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                </Link>
                <button
                  onClick={handleLogout}
                  className="text-[10px] tracking-[0.15em] uppercase text-zinc-600 hover:text-zinc-300 transition-colors px-3 py-1.5 border border-transparent hover:border-zinc-800"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
        <Outlet />
      </main>

      {/* Bottom status bar */}
      <footer className="fixed bottom-0 left-0 right-0 z-40 border-t border-zinc-800/50 bg-zinc-950/90 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">
              System Active
            </span>
          </div>
          <span className="text-[9px] tracking-[0.15em] uppercase text-zinc-700">
            Matcha Recruit v1.0
          </span>
        </div>
      </footer>
    </div>
  );
}
