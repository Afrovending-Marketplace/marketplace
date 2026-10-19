export const STATUS_TONE = { draft: "neutral", pending_review: "gold", active: "success", rejected: "danger", archived: "indigo" };
export const STATUS_LABEL = { draft: "Draft", pending_review: "Pending review", active: "Active", rejected: "Rejected", archived: "Archived" };
export const STOCK_REASONS = [["restock", "Restock"], ["correction", "Count correction"], ["damaged", "Damaged"], ["lost", "Lost"], ["returned", "Returned"]];

export const toMinor = (v) => Math.round(parseFloat(String(v).replace(/[$,]/g, "")) * 100);
export const fromMinor = (m) => (m == null ? "" : (m / 100).toFixed(2));
export const money = (m) => (m == null ? "—" : `$${(m / 100).toFixed(2)}`);
export const priceRange = (p) => (p.price_min_minor === p.price_max_minor ? money(p.price_min_minor) : `${money(p.price_min_minor)} – ${money(p.price_max_minor)}`);

export const productFields = (p) => ({
  title: p.title, description: p.description || "", category_slug: p.category_slug, tags: p.tags || [], sku: p.sku,
  price_minor: p.price_minor, currency: p.currency || "USD", option_names: p.option_names || [], low_stock_threshold: p.low_stock_threshold ?? 5,
});

export const flatCategories = (cats) => cats.flatMap((c) => [{ slug: c.slug, name: c.name }, ...(c.children || []).map((k) => ({ slug: k.slug, name: `${c.name} › ${k.name}` }))]);

export const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
};
