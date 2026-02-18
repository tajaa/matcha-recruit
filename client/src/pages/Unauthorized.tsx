import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';

function getHomePath(role?: UserRole): string {
  switch (role) {
    case 'candidate':
      return '/app/jobs';
    case 'employee':
      return '/app/portal';
    case 'broker':
      return '/app/broker/clients';
    case 'admin':
    case 'client':
      return '/app';
    default:
      return '/';
  }
}

export function Unauthorized() {
  const navigate = useNavigate();
  const { user, isLoading } = useAuth();
  const homePath = getHomePath(user?.role);

  // Authenticated users should never stay on this page — redirect them home.
  // This handles the case where the post-login `from` redirect targets a route
  // the current user's role can't access (e.g. different account than last session).
  useEffect(() => {
    if (!isLoading && user) {
      navigate(homePath, { replace: true });
    }
  }, [isLoading, user, homePath, navigate]);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="text-center">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-6">
          <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-white mb-2">Access Denied</h1>
        <p className="text-zinc-400 mb-6">You don't have permission to access this page.</p>
        <Button onClick={() => navigate(homePath, { replace: true })}>Go to Home</Button>
      </div>
    </div>
  );
}

export default Unauthorized;
