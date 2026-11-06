import { api } from "@/lib/api";

const CONSENT_KEY = "av_consent";
const ANON_KEY = "av_anon";
const REF_KEY = "av_ref";
let queue = [];
let timer = null;
let gaReady = false;

export const getConsent = () => {
  try {
    return JSON.parse(localStorage.getItem(CONSENT_KEY));
  } catch {
    return null;
  }
};

const anonId = () => {
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
};

const GA_MAP = { product_view: "view_item", search: "search", add_to_cart: "add_to_cart", begin_checkout: "begin_checkout", page_view: "page_view" };

const loadGa = async () => {
  if (gaReady) return;
  const { data } = await api.get("/marketing/config").catch(() => ({ data: {} }));
  const id = data.ga4_measurement_id;
  if (!id || !getConsent()?.analytics) return;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", id, { anonymize_ip: true, send_page_view: false });
  gaReady = true;
};

export const setConsent = (c) => {
  localStorage.setItem(CONSENT_KEY, JSON.stringify({ ...c, at: new Date().toISOString() }));
  window.dispatchEvent(new Event("av:consent"));
  if (c.analytics) loadGa();
};

const flush = () => {
  timer = null;
  if (!queue.length) return;
  const events = queue.splice(0, 20);
  api.post("/analytics/events", { anon_id: anonId(), events }).catch(() => {});
};

/** No-op unless the visitor accepted analytics cookies. Never pass names, emails or addresses. */
export const track = (type, data = {}) => {
  if (!getConsent()?.analytics) return;
  queue.push({ type, event_id: crypto.randomUUID(), path: window.location.pathname, ...data });
  if (gaReady && window.gtag && GA_MAP[type]) window.gtag("event", GA_MAP[type], { item_id: data.product_slug, search_term: data.query });
  if (!timer) timer = setTimeout(flush, 1500);
};

export const initAnalytics = () => {
  if (getConsent()?.analytics) loadGa();
};

export const captureReferral = (search) => {
  const code = new URLSearchParams(search).get("ref");
  if (!code || !/^[A-Za-z0-9]{4,20}$/.test(code)) return;
  if (!localStorage.getItem(REF_KEY)) localStorage.setItem(REF_KEY, code.toUpperCase());
  track("referral_visit", { referral_code: code.toUpperCase() });
};

export const storedReferral = () => localStorage.getItem(REF_KEY) || "";
