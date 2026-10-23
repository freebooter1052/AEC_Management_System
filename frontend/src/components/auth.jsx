import { createContext, useContext, useState } from "react";
import { api, session } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => (session.token ? session.user : null));

  const value = {
    user,
    signIn(token, u) { session.save(token, u); setUser(u); },
    /** Swap in the fresh token after a password change (the API revoked the old one). */
    refreshSession(token, u) { session.save(token, u); setUser(u); },
    updateUser(u) { session.save(session.token, u); setUser(u); },
    async signOut() {
      try { await api("/auth/logout/", { method: "POST" }); } catch (e) { /* token may already be invalid */ }
      session.clear();
      // replace(), not href: the signed-in page must not stay in history for the Back button.
      window.location.replace("/login/");
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
