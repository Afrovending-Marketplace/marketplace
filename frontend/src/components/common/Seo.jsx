import { useEffect } from "react";

const SITE = "AfroVending";
const upsert = (selector, make) => {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = make();
    document.head.appendChild(el);
  }
  return el;
};
const meta = (attr, key, content) => {
  const el = upsert(`meta[${attr}="${key}"]`, () => Object.assign(document.createElement("meta"), { [attr === "name" ? "name" : "content"]: "" }));
  el.setAttribute(attr, key);
  el.setAttribute("content", content || "");
};

/** Title, description, canonical, Open Graph/Twitter tags and optional JSON-LD for the current page. */
export const Seo = ({ title, description, path, image, type = "website", jsonLd, noindex }) => {
  useEffect(() => {
    const full = title ? `${title} | ${SITE}` : `${SITE} — African marketplace`;
    const origin = /(^|\.)afrovending\.com$/.test(window.location.hostname) ? "https://afrovending.com" : window.location.origin;
    const url = `${origin}${path ?? window.location.pathname}`;
    document.title = full;
    meta("name", "description", description);
    meta("name", "robots", noindex ? "noindex,nofollow" : "index,follow");
    meta("property", "og:title", full);
    meta("property", "og:description", description);
    meta("property", "og:type", type);
    meta("property", "og:url", url);
    meta("property", "og:site_name", SITE);
    meta("name", "twitter:card", image ? "summary_large_image" : "summary");
    if (image) meta("property", "og:image", image.startsWith("/") ? `${window.location.origin}${image}` : image);
    upsert('link[rel="canonical"]', () => Object.assign(document.createElement("link"), { rel: "canonical" })).setAttribute("href", url);
    const ld = document.getElementById("av-jsonld");
    if (ld) ld.remove();
    if (jsonLd) {
      const s = Object.assign(document.createElement("script"), { id: "av-jsonld", type: "application/ld+json", text: JSON.stringify(jsonLd) });
      document.head.appendChild(s);
    }
  }, [title, description, path, image, type, jsonLd, noindex]);
  return null;
};

export const productJsonLd = (p, url) => ({
  "@context": "https://schema.org", "@type": "Product", name: p.title, description: p.description, image: p.image ? [p.image] : undefined, url,
  brand: { "@type": "Brand", name: p.vendorName || p.vendor_name || SITE },
  offers: { "@type": "Offer", priceCurrency: "USD", price: ((p.price_minor ?? Math.round((p.price || 0) * 100)) / 100).toFixed(2), url,
    availability: "https://schema.org/InStock", seller: { "@type": "Organization", name: p.vendorName || p.vendor_name || SITE } },
});
