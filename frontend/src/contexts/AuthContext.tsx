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
async function resolveTenancyRole(): Promise<string> {
  try {
    const roleData = await getRole();
    return roleData?.role || 'client';
  } catch {
    return 'client';
  }
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
