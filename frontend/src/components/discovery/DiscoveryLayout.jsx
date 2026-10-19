import { Link } from "react-router-dom";
import { AlertTriangle, Loader2, SearchX, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { SortSelect } from "@/components/commerce/SortSelect";
import { FilterPanel } from "@/components/discovery/FilterPanel";
import { getCategory, getVendor, RELEVANCE, SORTS } from "@/lib/catalog";
import { useDiscovery } from "@/lib/search";

const Chips = ({ state, update, baseCategory }) => {
  const chips = [
    state.category && state.category !== baseCategory && ["category", getCategory(state.category)?.name || state.category],
    ...(state.vendor ? state.vendor.split(",").map((v) => [`vendor:${v}`, getVendor(v)?.name || v]) : []),
    (state.min || state.max) && ["price", `$${state.min || "0"} – ${state.max ? `$${state.max}` : "any"}`],
    state.in_stock && ["in_stock", "In stock"],
  ].filter(Boolean);
  if (!chips.length) return null;
  const remove = (k) => (k.startsWith("vendor:") ? update({ vendor: state.vendor.split(",").filter((v) => v !== k.slice(7)).join(",") })
    : update(k === "price" ? { min: "", max: "" } : { [k]: "" }));
  return (
    <div className="flex flex-wrap gap-2" data-testid="active-filters">
      {chips.map(([k, label]) => (
        <button key={k} type="button" onClick={() => remove(k)} data-testid={`active-filter-${k.replace(":", "-")}`}
          className="inline-flex items-center gap-1 rounded-full border border-av-line bg-white px-3 py-1 text-xs hover:border-av-ink/40">{label} <X className="h-3 w-3" /></button>
      ))}
    </div>
  );
};

const Empty = ({ q, activeCount, clear, empty }) => (
  <div data-testid="search-empty" className="rounded-2xl border border-dashed border-av-line p-10 text-center">
    <SearchX className="mx-auto h-8 w-8 text-av-muted" />
    <p className="mt-3 font-serif text-2xl text-av-ink">{q ? `No results for “${q}”` : "No products match"}</p>
    <p className="mt-2 text-sm text-av-muted">{activeCount ? "Try removing a filter." : q ? "Check the spelling or try a broader word, like “dress” or “spice”." : empty}</p>
    <div className="mt-6 flex flex-wrap justify-center gap-3">
      {activeCount > 0 && <Button variant="outline" onClick={clear} data-testid="empty-clear-filters">Clear filters</Button>}
      <Button asChild variant="outline"><Link to="/categories" data-testid="empty-browse-categories">Browse categories</Link></Button>
    </div>
  </div>
);

export const DiscoveryLayout = ({ baseCategory = "", empty = "Vendors will list items here soon." }) => {
  const { state, res, update, clear, loadMore, retry, activeCount } = useDiscovery(baseCategory);
  const panel = <FilterPanel facets={res.facets} state={state} update={update} clear={clear} activeCount={activeCount} baseCategory={baseCategory} />;
  const sorts = state.q ? [RELEVANCE, ...SORTS] : SORTS;
  return (
    <div className="av-container py-10 lg:py-14">
      <DevDataNotice className="mb-8" />
      <div className="grid gap-10 lg:grid-cols-[240px_1fr]">
        <div className="hidden lg:block">{panel}</div>
        <div className="min-w-0 space-y-6">
          <div className="flex items-center gap-3 lg:hidden">
            <Sheet>
              <SheetTrigger asChild><Button variant="outline" size="sm" data-testid="mobile-filters-button"><SlidersHorizontal /> Filters{activeCount ? ` (${activeCount})` : ""}</Button></SheetTrigger>
              <SheetContent side="left" className="w-[85vw] max-w-sm overflow-y-auto bg-av-linen" data-testid="mobile-filters-sheet">
                <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader><div className="mt-6">{panel}</div>
              </SheetContent>
            </Sheet>
          </div>
          <SortSelect value={state.sort} onChange={(v) => update({ sort: v })} count={res.total} options={sorts} />
          <Chips state={state} update={update} baseCategory={baseCategory} />
          {res.error ? (
            <div data-testid="search-error" role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center text-red-800">
              <AlertTriangle className="mx-auto h-6 w-6" /><p className="mt-2">{res.error}</p>
              <Button variant="outline" className="mt-4" onClick={retry} data-testid="search-retry">Try again</Button>
            </div>
          ) : res.loading ? (
            <div data-testid="search-loading" className="grid place-items-center py-24"><Loader2 className="h-6 w-6 animate-spin text-av-muted" /></div>
          ) : res.data.length ? (
            <>
              <ProductGrid products={res.data} testId="listing-product-grid" />
              <div className="flex flex-col items-center gap-3 pt-4">
                <p className="text-xs text-av-muted" data-testid="search-showing">Showing {res.data.length} of {res.total}</p>
                {res.has_more && <Button variant="outline" onClick={loadMore} disabled={res.loadingMore} data-testid="search-load-more">{res.loadingMore && <Loader2 className="animate-spin" />} Load more</Button>}
              </div>
            </>
          ) : <Empty q={state.q} activeCount={activeCount} clear={clear} empty={empty} />}
        </div>
      </div>
    </div>
  );
};
