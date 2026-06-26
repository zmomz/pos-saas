import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from 'react';
import { authApi } from '../lib/auth';
import { getRole } from '../lib/api';

interface User {
  id: string;
  email: string;
  name?: string;
  role: string; // tenancy role: master | agent | client
  must_change_password?: boolean;
  last_login?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

// Resolve the multi-tenant role (master/agent/client) for the signed-in user.
//
// FE-06: a transient /tenant/role failure must NOT silently reassign a master or
// agent to the least-privileged 'client' role. The backend always returns 200
// with an explicit role for an authenticated user (defaulting to 'client'
// itself), so a thrown error here is purely a transport/auth blip — we retry a
// few times and, if it still fails, propagate the error to the caller instead of
// fabricating a role. Authorization downgrade is never the right answer to a
// network error.
export async function resolveTenancyRole(
  retries = 2,
  delayMs = 300,
): Promise<string> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const roleData = await getRole();
      return roleData?.role || 'client';
    } catch (err) {
      lastErr = err;
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastErr;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkAuthStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const userData = await authApi.getCurrentUser();
      if (userData) {
        const role = await resolveTenancyRole();
        setUser({ ...userData, role });
      } else {
        setUser(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    setError(null);
    const userData = await authApi.login(email, password);
    const role = await resolveTenancyRole();
    setUser({ ...userData, role });
  };

  const register = async (email: string, password: string, name?: string) => {
    setError(null);
    const userData = await authApi.register(email, password, name);
    const role = await resolveTenancyRole();
    setUser({ ...userData, role });
  };

  const logout = async () => {
    setError(null);
    try {
      await authApi.logout();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Logout failed');
    } finally {
      setUser(null);
    }
  };

  useEffect(() => {
    checkAuthStatus();
  }, []);

  const value: AuthContextType = {
    user,
    loading,
    error,
    login,
    register,
    logout,
    refetch: checkAuthStatus,
    isAdmin: user?.role === 'master',
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
