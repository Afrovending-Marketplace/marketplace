// Catalog read layer. Uses the live /api/v1/catalog snapshot once approved products exist; otherwise the labelled development data.
import { CATEGORIES as DEV_CATEGORIES, VENDORS as DEV_VENDORS, PRODUCTS as DEV_PRODUCTS } from "@/data/dev/catalog";

let CATEGORIES = DEV_CATEGORIES;
let VENDORS = DEV_VENDORS;
let PRODUCTS = DEV_PRODUCTS;
let LIVE = false;

const FALLBACK_IMAGE = "/images/weaving.jpg";
const DEV_IMAGES = Object.fromEntries(DEV_CATEGORIES.map((c) => [c.slug, c.image]));
export const absUrl = (u) => (u && u.startsWith("/api/") ? `${process.env.REACT_APP_BACKEND_URL}${u}` : u);

export const normalizeProduct = (p) => ({ ...p, images: p.images?.length ? p.images.map(absUrl) : [FALLBACK_IMAGE] });

export const setCatalog = ({ categories, products, vendors }) => {
  if (categories?.length) CATEGORIES = categories.map((c) => ({ ...c, image: c.image || DEV_IMAGES[c.slug] || FALLBACK_IMAGE }));
  if (products?.length) {
    LIVE = true;
    PRODUCTS = products.map(normalizeProduct);
    VENDORS = vendors.map((v) => ({ ...v, logo: absUrl(v.logo) || "/logo-mark.png", banner: absUrl(v.banner) || FALLBACK_IMAGE }));
  }
};

export const isDevData = () => !LIVE;
export const IS_DEV_DATA = true;

const childSlugs = (slug) => [slug, ...((CATEGORIES.find((c) => c.slug === slug)?.children || []).map((k) => k.slug))];

export const getCategories = () => CATEGORIES;
export const getCategory = (slug) => {
  const top = CATEGORIES.find((c) => c.slug === slug);
  if (top) return top;
  const parent = CATEGORIES.find((c) => c.children?.some((k) => k.slug === slug));
  const child = parent?.children.find((k) => k.slug === slug);
  return child ? { ...child, image: parent.image, blurb: parent.blurb, subcategories: [] } : undefined;
};
export const getVendors = () => VENDORS;
export const getVendor = (slug) => VENDORS.find((v) => v.slug === slug);
export const getProducts = () => PRODUCTS;
export const getProduct = (slug) => PRODUCTS.find((p) => p.slug === slug);
export const getProductsByCategory = (slug) => {
  const slugs = childSlugs(slug);
  return PRODUCTS.filter((p) => slugs.includes(p.category_slug));
};
export const getProductsByVendor = (slug) => PRODUCTS.filter((p) => p.vendor_slug === slug);
export const getFeaturedProducts = () => (LIVE ? PRODUCTS.slice(0, 8) : PRODUCTS.filter((p) => p.is_featured));
export const getFeaturedVendors = () => VENDORS.slice(0, 4);

export const getNewArrivals = (n = 4) =>
  [...PRODUCTS].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, n);

export const getRelatedProducts = (product, n = 4) =>
  PRODUCTS.filter((p) => p.category_slug === product.category_slug && p.slug !== product.slug)
    .concat(PRODUCTS.filter((p) => p.vendor_slug === product.vendor_slug && p.category_slug !== product.category_slug))
    .slice(0, n);

export const searchProducts = (q) => localSearch({ q, limit: 500 }).data;

const hay = (p) => `${p.title} ${(p.tags || p.details || []).join(" ")} ${p.category_slug} ${p.description || ""}`.toLowerCase();
const words = (q) => (q || "").toLowerCase().split(/\s+/).filter((w) => w.length > 1);
const score = (p, ws) => ws.reduce((s, w) => s + (p.title.toLowerCase().includes(w) ? 10 : 0) + ((p.tags || p.details || []).join(" ").toLowerCase().includes(w) ? 5 : 0) + 1, 0);

// Development-data mirror of GET /api/v1/catalog/search (same params and response shape).
export const localSearch = ({ q = "", category = "", vendor = "", min = "", max = "", in_stock = false, sort = "relevance", page = 1, limit = 24 }) => {
  const ws = words(q);
  const base = PRODUCTS.filter((p) => ws.every((w) => hay(p).includes(w)));
  const cats = category ? childSlugs(category) : null;
  const vendors = vendor ? vendor.split(",") : null;
  let list = base.filter((p) => (!cats || cats.includes(p.category_slug)) && (!vendors || vendors.includes(p.vendor_slug))
    && (min === "" || p.price_minor >= Number(min) * 100) && (max === "" || p.price_minor <= Number(max) * 100) && (!in_stock || p.in_stock !== false));
  const effective = sort === "relevance" && !ws.length ? "featured" : sort;
  list = effective === "relevance" ? [...list].sort((a, b) => score(b, ws) - score(a, ws)) : sortProducts(list, effective);
  const count = (slugs) => base.filter((p) => slugs.includes(p.category_slug)).length;
  const scoped = cats ? base.filter((p) => cats.includes(p.category_slug)) : base;
  const vendorCounts = VENDORS.map((v) => ({ slug: v.slug, name: v.name, count: scoped.filter((p) => p.vendor_slug === v.slug).length })).filter((v) => v.count);
  const prices = scoped.map((p) => p.price_minor);
  const facets = {
    categories: CATEGORIES.map((c) => ({ ...c, product_count: count(childSlugs(c.slug)), children: (c.children || []).map((k) => ({ ...k, product_count: count([k.slug]) })) })).filter((c) => c.product_count),
    vendors: vendorCounts.sort((a, b) => b.count - a.count), price: { min: prices.length ? Math.min(...prices) : null, max: prices.length ? Math.max(...prices) : null },
    in_stock: scoped.filter((p) => p.in_stock !== false).length,
  };
  return { data: list.slice((page - 1) * limit, page * limit), total: list.length, has_more: page * limit < list.length, page, limit, mode: ws.length ? "text" : "browse", sort: effective, facets };
};

export const localSuggest = (q) => {
  const t = q.trim().toLowerCase();
  const kws = [...new Set(PRODUCTS.flatMap((p) => p.tags || p.details || []).map((x) => x.toLowerCase()).filter((x) => x.includes(t) && x.length < 30))].slice(0, 5);
  return {
    query: q, keywords: kws,
    products: PRODUCTS.filter((p) => p.title.toLowerCase().includes(t)).slice(0, 5).map((p) => ({ title: p.title, slug: p.slug, price_minor: p.price_minor, currency: p.currency })),
    categories: CATEGORIES.filter((c) => c.name.toLowerCase().includes(t)).slice(0, 4).map((c) => ({ slug: c.slug, name: c.name })),
    vendors: VENDORS.filter((v) => v.name.toLowerCase().includes(t)).slice(0, 3).map((v) => ({ slug: v.slug, name: v.name })),
  };
};

export const RELEVANCE = ["relevance", "Best match"];

export const SORTS = [
  ["featured", "Featured"],
  ["newest", "Newest"],
  ["price-asc", "Price: low to high"],
  ["price-desc", "Price: high to low"],
];

export const sortProducts = (list, sort) => {
  const out = [...list];
  if (sort === "newest") out.sort((a, b) => b.created_at.localeCompare(a.created_at));
  if (sort === "price-asc") out.sort((a, b) => a.price_minor - b.price_minor);
  if (sort === "price-desc") out.sort((a, b) => b.price_minor - a.price_minor);
  if (sort === "featured") out.sort((a, b) => Number(b.is_featured) - Number(a.is_featured));
  return out;
};

export const formatPrice = (minor, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency }).format(minor / 100);
