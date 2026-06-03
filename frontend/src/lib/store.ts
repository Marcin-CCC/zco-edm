import { create } from 'zustand';

interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  role: string;
  is_active: boolean;
  is_admin?: boolean;
  created_at: string;
  updated_at: string;
  last_login?: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  setUser: (user: User) => void;
}

function getStoredUser(): User | null {
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('auth_user');
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch {
        return null;
      }
    }
  }
  return null;
}

function getInitialToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('auth_token');
  }
  return null;
}

export const useAuth = create<AuthState>((set) => {
  const token = getInitialToken();
  const user = getStoredUser();

  return {
    token,
    user: user,
    isAuthenticated: !!token,

    login: (token, user) => {
      if (typeof window !== 'undefined') {
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_user', JSON.stringify(user));
      }
      set({ token, user, isAuthenticated: true });
    },

    logout: () => {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
      }
      set({ token: null, user: null, isAuthenticated: false });
    },

    setUser: (user) => set({ user }),
  };
});
