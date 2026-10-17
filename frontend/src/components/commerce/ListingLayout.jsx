import { FilterSidebar } from "@/components/commerce/FilterSidebar";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { SortSelect, useSort } from "@/components/commerce/SortSelect";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { sortProducts } from "@/lib/catalog";

export const ListingLayout = ({ products, activeSlug, subcategories, empty }) => {
  const [sort, setSort] = useSort();
  const sorted = sortProducts(products, sort);
  return (
    <div className="av-container py-10 lg:py-14">
      <DevDataNotice className="mb-8" />
      <div className="grid gap-10 lg:grid-cols-[220px_1fr]">
        <div className="hidden lg:block"><FilterSidebar activeSlug={activeSlug} subcategories={subcategories} /></div>
        <div className="min-w-0 space-y-8">
          <SortSelect value={sort} onChange={setSort} count={sorted.length} />
          {sorted.length ? <ProductGrid products={sorted} testId="listing-product-grid" /> : empty}
        </div>
      </div>
    </div>
  );
};
