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

export const searchProducts = (q) => {
  const term = q.trim().toLowerCase();
  if (!term) return [];
  return PRODUCTS.filter((p) => `${p.title} ${p.category_slug} ${(p.tags || []).join(" ")} ${getVendor(p.vendor_slug)?.name}`.toLowerCase().includes(term));
};

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
