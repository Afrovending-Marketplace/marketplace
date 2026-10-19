import { useSearchParams } from "react-router-dom";
import { PageHero } from "@/components/common/PageHero";
import { DiscoveryLayout } from "@/components/discovery/DiscoveryLayout";
import { SearchBox } from "@/components/layout/SearchEntry";

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  return (
    <div data-testid="search-page">
      <PageHero eyebrow="Search" title={q ? `Results for “${q}”` : "Search"} crumbs={[{ label: "Home", to: "/" }, { label: "Search" }]}
        description="Search products by name, tag or category, then narrow down with filters." />
      <div className="av-container -mb-4 pt-8"><div className="max-w-xl"><SearchBox key={q} initial={q} testPrefix="search-page" /></div></div>
      <DiscoveryLayout />
    </div>
  );
}
