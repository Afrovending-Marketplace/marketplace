import axios from "axios";

export const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/v1`,
  timeout: 20000,
  withCredentials: true,
});

let refreshing = null;
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const cfg = error.config;
    const url = cfg?.url || "";
    if (error.response?.status === 401 && !cfg._retried && !url.startsWith("/auth/")) {
      cfg._retried = true;
      refreshing = refreshing || api.post("/auth/refresh").finally(() => { refreshing = null; });
      try {
        await refreshing;
        return api(cfg);
      } catch {
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);

export const getErrorMessage = (err) => {
  const e = err?.response?.data?.error;
  if (e?.details?.length && typeof e.details[0]?.message === "string") return e.details.map((d) => d.message).join(" ");
  if (typeof e?.message === "string") return e.message;
  return "Something went wrong. Please try again.";
};
