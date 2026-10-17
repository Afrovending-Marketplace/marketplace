import { PageHero } from "@/components/common/PageHero";
import { CategoryTile } from "@/components/commerce/CategoryTile";
import { getCategories } from "@/lib/catalog";

export default function CategoriesPage() {
  return (
    <div data-testid="categories-page">
      <PageHero eyebrow="Browse" title="All categories" crumbs={[{ label: "Home", to: "/" }, { label: "Categories" }]}
        description="Nine departments celebrating culture, craft and everyday essentials." />
      <div className="av-container grid gap-5 py-12 sm:grid-cols-2 lg:grid-cols-3 lg:py-16">
        {getCategories().map((c) => <CategoryTile key={c.slug} category={c} className="min-h-[260px]" />)}
      </div>
    </div>
  );
}
