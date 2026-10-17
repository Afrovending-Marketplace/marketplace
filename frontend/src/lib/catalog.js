// Catalog read layer. Phase 01 reads development data; Phase 04+ swaps these for /api/v1 calls.
import { CATEGORIES, VENDORS, PRODUCTS } from "@/data/dev/catalog";

export const IS_DEV_DATA = true;

export const getCategories = () => CATEGORIES;
export const getCategory = (slug) => CATEGORIES.find((c) => c.slug === slug);
export const getVendors = () => VENDORS;
export const getVendor = (slug) => VENDORS.find((v) => v.slug === slug);
export const getProducts = () => PRODUCTS;
export const getProduct = (slug) => PRODUCTS.find((p) => p.slug === slug);
export const getProductsByCategory = (slug) => PRODUCTS.filter((p) => p.category_slug === slug);
export const getProductsByVendor = (slug) => PRODUCTS.filter((p) => p.vendor_slug === slug);
export const getFeaturedProducts = () => PRODUCTS.filter((p) => p.is_featured);
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
  return PRODUCTS.filter((p) => `${p.title} ${p.category_slug} ${getVendor(p.vendor_slug)?.name}`.toLowerCase().includes(term));
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
