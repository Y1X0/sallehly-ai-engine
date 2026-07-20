"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import * as api from "./apiClient";
import type { User } from "./types";

const TOKEN_STORAGE_KEY = "sallehly_token";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function hydrateFromStoredToken() {
      const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!stored) {
        return;
      }
      try {
        const fetchedUser = await api.getMe(stored);
        setToken(stored);
        setUser(fetchedUser);
      } catch {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      }
    }
    hydrateFromStoredToken().finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, response.token);
    setToken(response.token);
    setUser(response.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      await api.register(email, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
