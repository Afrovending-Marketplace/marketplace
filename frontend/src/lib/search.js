import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "@/lib/api";
import { isDevData, localSearch, localSuggest, normalizeProduct } from "@/lib/catalog";

const PAGE = 24;
const FILTER_KEYS = ["q", "category", "vendor", "min", "max", "in_stock", "sort"];

const fetchPage = async (state, page, limit) => {
  if (isDevData()) return localSearch({ ...state, page, limit });
  const params = Object.fromEntries(Object.entries({ ...state, in_stock: state.in_stock || undefined, page, limit }).filter(([, v]) => v !== "" && v !== undefined && v !== false));
  const r = await api.get("/catalog/search", { params });
  return { ...r.data, data: r.data.data.map(normalizeProduct) };
};

export const getSuggestions = async (q) => (isDevData() ? localSuggest(q) : (await api.get("/catalog/suggest", { params: { q } })).data);

// URL-driven search state shared by /shop, /search and /categories/:slug.
export const useDiscovery = (baseCategory = "") => {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const state = {
    q, category: params.get("category") || baseCategory, vendor: params.get("vendor") || "", min: params.get("min") || "", max: params.get("max") || "",
    in_stock: params.get("in_stock") === "1", sort: params.get("sort") || (q ? "relevance" : "featured"),
  };
  const key = JSON.stringify(state);
  const urlPage = Math.max(1, Number(params.get("page")) || 1);
  const [res, setRes] = useState({ data: [], total: 0, facets: null, loading: true, error: "", page: 1 });
  const pageRef = useRef(urlPage);
  pageRef.current = urlPage;
  const load = useCallback(async () => {
    setRes((r) => ({ ...r, loading: true, error: "" }));
    try {
      const pages = Math.min(pageRef.current, 5);
      const out = await fetchPage(JSON.parse(key), 1, PAGE * pages);
      setRes({ ...out, loading: false, error: "", page: pages, has_more: out.total > PAGE * pages });
    } catch (err) {
      setRes((r) => ({ ...r, data: [], total: 0, loading: false, error: getErrorMessage(err) }));
    }
  }, [key]);
  useEffect(() => {
    load();
  }, [load]);
  const update = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === "" || v === false || v == null || (k === "category" && v === baseCategory) ? next.delete(k) : next.set(k, v === true ? "1" : v)));
    next.delete("page");
    setParams(next);
  };
  const clear = () => setParams(q ? { q } : {});
  const loadMore = async () => {
    const page = res.page + 1;
    setRes((r) => ({ ...r, loadingMore: true }));
    try {
      const out = await fetchPage(state, page, PAGE);
      setRes((r) => ({ ...r, data: [...r.data, ...out.data], has_more: out.has_more, page, loadingMore: false }));
      const next = new URLSearchParams(params);
      next.set("page", String(page));
      setParams(next, { replace: true });
    } catch (err) {
      setRes((r) => ({ ...r, loadingMore: false, error: getErrorMessage(err) }));
    }
  };
  const activeCount = FILTER_KEYS.filter((k) => k !== "q" && k !== "sort" && params.get(k)).length;
  return { state, res, update, clear, loadMore, retry: load, activeCount };
};
