import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

const fetchMe = async () => {
  try {
    return (await api.get("/auth/me")).data.user;
  } catch {
    try {
      return (await api.post("/auth/refresh")).data.user;
    } catch {
      return false;
    }
  }
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null = checking, false = signed out

  useEffect(() => {
    fetchMe().then(setUser);
  }, []);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    const me = (await api.get("/auth/me").catch(() => ({ data })))?.data?.user || data.user;
    setUser(me);
    return me;
  }, []);

  const register = useCallback(async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(false);
  }, []);

  const reload = useCallback(async () => setUser(await fetchMe()), []);

  return <AuthContext.Provider value={{ user, setUser, login, register, logout, reload }}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);

export const isAdmin = (user) => !!user && user.roles.some((r) => r.endsWith("admin"));
