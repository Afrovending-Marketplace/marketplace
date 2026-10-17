import { Link } from "react-router-dom";
import { SectionHeading } from "@/components/common/SectionHeading";
import { CategoryTile } from "@/components/commerce/CategoryTile";
import { getCategories, getCategory } from "@/lib/catalog";
import { HOME } from "@/constants/testIds";

const TRENDING = [
  ["fashion", "md:col-span-5 md:row-span-2"],
  ["home-living", "md:col-span-7"],
  ["beauty", "md:col-span-4"],
  ["jewelry", "md:col-span-3"],
];

export const ShopByCategory = () => (
  <section data-testid="home-shop-by-category" className="av-container py-16 lg:py-20">
    <div className="mb-8 flex items-end justify-between gap-4">
      <SectionHeading eyebrow="Browse" title="Shop by category" />
      <Link to="/categories" data-testid="home-all-categories-link" className="text-sm font-semibold text-av-clay hover:underline underline-offset-4">All categories</Link>
    </div>
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-9">
      {getCategories().map((c) => <CategoryTile key={c.slug} category={c} size="sm" />)}
    </div>
  </section>
);

export const TrendingCategories = () => (
  <section data-testid={HOME.categoryTeaser} className="bg-white border-y border-av-line">
    <div className="av-container py-16 lg:py-24">
      <SectionHeading eyebrow="Editor's picks" title="Trending categories"
        description="A curated selection. Trend rankings will use real marketplace activity once live data exists." />
      <div className="mt-10 grid gap-4 md:grid-cols-12 md:auto-rows-[220px]">
        {TRENDING.map(([slug, span]) => <CategoryTile key={slug} category={getCategory(slug)} className={span} />)}
      </div>
    </div>
  </section>
);
