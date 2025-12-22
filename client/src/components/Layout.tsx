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
  { path: '/app/jobs', label: 'Job Search', roles: ['candidate'] },
  { path: '/app/test-bot', label: 'Test Bot', roles: ['admin', 'candidate'] },
  { path: '/app/import', label: 'Import', roles: ['admin'] },
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
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-sans selection:bg-matcha-500 selection:text-white">
      <nav className="fixed top-0 inset-x-0 z-50 bg-zinc-900/80 backdrop-blur-md border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-8">
              <div className="flex-shrink-0 flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-matcha-500 flex items-center justify-center text-zinc-950 font-bold text-lg">
                  M
                </div>
                <div>
                  <span className="text-xl font-bold text-white tracking-tight">Matcha</span>
                  <span className="text-xl font-light text-zinc-500 ml-1">Recruit</span>
                </div>
              </div>
              <div className="hidden sm:flex sm:space-x-1">
                {navItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`inline-flex items-center px-3 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                      location.pathname === item.path
                        ? 'text-matcha-400 bg-matcha-500/10'
                        : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
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
                <div className="text-sm hidden md:block">
                  <span className="text-zinc-500">Signed in as </span>
                  <span className="text-white">{user.email}</span>
                  <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-matcha-500/20 text-matcha-400 capitalize">
                    {user.role}
                  </span>
                </div>
                <Link
                  to="/app/settings"
                  className={`text-sm transition-colors px-3 py-1.5 rounded-md ${
                    location.pathname === '/app/settings'
                      ? 'text-matcha-400 bg-matcha-500/10'
                      : 'text-zinc-400 hover:text-white hover:bg-white/5'
                  }`}
                  title="Settings"
                >
                  <svg
                    className="w-5 h-5"
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
                  className="text-sm text-zinc-400 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-white/5"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-12">
        <Outlet />
      </main>
    </div>
  );
}
