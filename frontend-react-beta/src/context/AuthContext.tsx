import { createContext, useCallback, useContext, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { AuthTokenResponse } from '@/types';

const USER_ID_KEY = 'ami_user_id';
const AUTH_TOKEN_KEY = 'auth_token';

function readStoredUserId(): string | null {
  try {
    return localStorage.getItem(USER_ID_KEY);
  } catch {
    return null;
  }
}

interface AuthContextValue {
  userId: string | null;
  isAuthenticated: boolean;
  login(data: AuthTokenResponse): void;
  logout(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserId] = useState<string | null>(readStoredUserId);
  const queryClient = useQueryClient();

  const login = useCallback((data: AuthTokenResponse) => {
    try {
      localStorage.setItem(USER_ID_KEY, data.username);
    } catch {
      // ignore
    }
    setUserId(data.username);
  }, []);

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(USER_ID_KEY);
      localStorage.removeItem(AUTH_TOKEN_KEY);
    } catch {
      // ignore
    }
    setUserId(null);
    queryClient.clear();
  }, [queryClient]);

  return (
    <AuthContext.Provider value={{ userId, isAuthenticated: userId !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuthContext must be used within AuthProvider');
  return ctx;
}

