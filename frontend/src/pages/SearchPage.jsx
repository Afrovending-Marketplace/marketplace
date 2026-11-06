import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHero } from "@/components/common/PageHero";
import { Seo } from "@/components/common/Seo";
import { DiscoveryLayout } from "@/components/discovery/DiscoveryLayout";
import { SearchBox } from "@/components/layout/SearchEntry";
import { api } from "@/lib/api";
import { track } from "@/lib/analytics";

const Sponsored = ({ q }) => {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/sponsored", { params: { q } }).then((r) => setD(r.data)).catch(() => setD(null));
  }, [q]);
  if (!d?.enabled || !d.items.length) return null;
  return (
    <section className="av-container pt-6" data-testid="sponsored-results" aria-label="Sponsored products">
      <p className="text-xs font-semibold uppercase tracking-wide text-av-muted">{d.label} · paid placements, separate from search results</p>
      <ul className="mt-2 flex flex-wrap gap-2">{d.items.map((p) => <li key={p.slug}><Link to={`/products/${p.slug}`} className="rounded-full border px-3 py-1 text-sm">{d.label}: {p.title}</Link></li>)}</ul>
    </section>
  );
};

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  useEffect(() => {
    if (q) track("search", { query: q.slice(0, 120) });
  }, [q]);
  return (
    <div data-testid="search-page">
      <Seo title={q ? `Search: ${q}` : "Search"} description="Search African fashion, beauty, food and crafts on AfroVending." noindex />
      <PageHero eyebrow="Search" title={q ? `Results for “${q}”` : "Search"} crumbs={[{ label: "Home", to: "/" }, { label: "Search" }]}
        description="Search products by name, tag or category, then narrow down with filters." />
      <div className="av-container -mb-4 pt-8"><div className="max-w-xl"><SearchBox key={q} initial={q} testPrefix="search-page" /></div></div>
      <Sponsored q={q} />
      <DiscoveryLayout />
    </div>
  );
}
