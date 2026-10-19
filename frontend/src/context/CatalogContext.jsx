import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { setCatalog } from "@/lib/catalog";

export const CatalogProvider = ({ children }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const done = setTimeout(() => setReady(true), 5000);
    api.get("/catalog/storefront")
      .then((r) => setCatalog(r.data))
      .catch(() => {})
      .finally(() => { clearTimeout(done); setReady(true); });
    return () => clearTimeout(done);
  }, []);
  if (!ready) {
    return (
      <div data-testid="catalog-loading" className="grid min-h-screen place-items-center bg-av-linen">
        <img src="/logo-mark.png" alt="AfroVending" className="h-14 w-14 animate-pulse" />
      </div>
    );
  }
  return children;
};
