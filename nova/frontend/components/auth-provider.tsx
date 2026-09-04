"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { login, logout, refreshSession, register } from "@/lib/api";
import { AuthContext } from "@/hooks/use-auth";
import type { User } from "@/types/auth";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const applySession = useCallback((token: string, sessionUser: User) => {
    setAccessToken(token);
    setUser(sessionUser);
  }, []);

  useEffect(() => {
    let mounted = true;
    refreshSession()
      .then((session) => {
        if (mounted) {
          applySession(session.access_token, session.user);
        }
      })
      .catch(() => {
        // A missing refresh cookie simply means the visitor is signed out.
      })
      .finally(() => {
        if (mounted) {
          setIsLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [applySession]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const session = await login(email, password);
      applySession(session.access_token, session.user);
    },
    [applySession],
  );

  const signUp = useCallback(
    async (email: string, password: string) => {
      const session = await register(email, password);
      applySession(session.access_token, session.user);
    },
    [applySession],
  );

  const signOut = useCallback(async () => {
    try {
      await logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, accessToken, isLoading, signIn, signUp, signOut }),
    [user, accessToken, isLoading, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
