import { Link, useSearchParams } from "react-router-dom";
import { PageHero } from "@/components/common/PageHero";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { CategoryTile } from "@/components/commerce/CategoryTile";
import { getCategories, searchProducts } from "@/lib/catalog";

export default function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  const results = searchProducts(q);
  return (
    <div data-testid="search-page">
      <PageHero eyebrow="Search preview" title={q ? `Results for “${q}”` : "Search"} crumbs={[{ label: "Home", to: "/" }, { label: "Search" }]}
        description="Simple title matching over development data. Full search, filters and ranking arrive in Phase 05." />
      <div className="av-container py-12 space-y-10">
        <DevDataNotice />
        {results.length ? (
          <>
            <p data-testid="search-result-count" className="text-sm text-av-muted">{results.length} matching {results.length === 1 ? "item" : "items"}</p>
            <ProductGrid products={results} testId="search-results-grid" />
          </>
        ) : (
          <div data-testid="search-empty" className="space-y-6">
            <p className="text-av-ink">{q ? "No matches in development data." : "Enter a search term from the search bar."} Browse a category instead:</p>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-9">
              {getCategories().map((c) => <CategoryTile key={c.slug} category={c} size="sm" />)}
            </div>
            <Link to="/shop" className="text-sm font-semibold text-av-clay hover:underline">Or shop all products →</Link>
          </div>
        )}
      </div>
    </div>
  );
}
