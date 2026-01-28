import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  roles?: UserRole[];
  requiredFeature?: string;
  anyRequiredFeature?: string[];
}

export function ProtectedRoute({ children, roles, requiredFeature, anyRequiredFeature }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, user, hasFeature } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-zinc-400">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (roles && user && !roles.includes(user.role)) {
    // Redirect employees to their portal instead of unauthorized
    if (user.role === 'employee') {
      return <Navigate to="/app/portal" replace />;
    }
    return <Navigate to="/unauthorized" replace />;
  }

  // Check feature flags (admin always passes via hasFeature)
  if (requiredFeature && !hasFeature(requiredFeature)) {
    if (user?.role === 'employee') {
      return <Navigate to="/app/portal" replace />;
    }
    return <Navigate to="/app" replace />;
  }

  if (anyRequiredFeature && !anyRequiredFeature.some(f => hasFeature(f))) {
    if (user?.role === 'employee') {
      return <Navigate to="/app/portal" replace />;
    }
    return <Navigate to="/app" replace />;
  }

  return <>{children}</>;
}
