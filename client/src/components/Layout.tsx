import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';

interface NavItem {
  path: string;
  label: string;
  roles: UserRole[];
}

const allNavItems: NavItem[] = [
  { path: '/', label: 'Companies', roles: ['admin', 'client'] },
  { path: '/positions', label: 'Positions', roles: ['admin', 'client', 'candidate'] },
  { path: '/candidates', label: 'Candidates', roles: ['admin', 'client'] },
  { path: '/jobs', label: 'Job Search', roles: ['candidate'] },
  { path: '/test-bot', label: 'Test Bot', roles: ['admin', 'candidate'] },
  { path: '/import', label: 'Import', roles: ['admin'] },
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
