import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

type UserRole = 'master' | 'agent' | 'client';

interface ProtectedRouteProps {
  allowedRoles?: UserRole[];
  children?: React.ReactNode;
}

const roleToPath: Record<UserRole, string> = {
  master: '/master',
  agent: '/agent',
  client: '/client',
};

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  allowedRoles,
  children,
}) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500 mx-auto mb-4"></div>
          <p className="text-slate-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // First-login force-reset: a freshly provisioned account must change its temp
  // password before reaching any protected page.
  if (user.must_change_password) {
    return <Navigate to="/force-reset" replace />;
  }

  const userRole = user.role as UserRole;

  if (allowedRoles && allowedRoles.length > 0 && !allowedRoles.includes(userRole)) {
    const redirectPath = roleToPath[userRole] || '/login';
    return <Navigate to={redirectPath} replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};

export default ProtectedRoute;