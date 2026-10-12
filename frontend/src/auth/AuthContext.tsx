import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { currentUser, loginAccount, logoutAccount, registerAccount } from '../api/auth';
import type { Credentials, User } from '../api/auth';

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (credentials: Credentials) => Promise<User>;
  register: (input: Credentials & { display_name: string }) => Promise<User>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    currentUser()
      .then((current) => active && setUser(current))
      .catch(() => active && setUser(null))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  async function login(credentials: Credentials) {
    const current = await loginAccount(credentials);
    setUser(current);
    return current;
  }

  async function register(input: Credentials & { display_name: string }) {
    const current = await registerAccount(input);
    setUser(current);
    return current;
  }

  async function logout() {
    await logoutAccount();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth must be used inside AuthProvider');
  return auth;
}