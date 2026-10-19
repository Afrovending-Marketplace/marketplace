import { useParams } from "react-router-dom";
import { Breadcrumbs } from "@/components/common/Breadcrumbs";
import { DiscoveryLayout } from "@/components/discovery/DiscoveryLayout";
import { getCategory } from "@/lib/catalog";
import NotFoundPage from "@/pages/NotFoundPage";

export default function CategoryPage() {
  const { slug } = useParams();
  const category = getCategory(slug);
  if (!category) return <NotFoundPage />;
  return (
    <div data-testid={`category-page-${slug}`}>
      <section className="relative overflow-hidden bg-av-indigo">
        <img src={category.image} alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-r from-av-indigo via-av-indigo/80 to-transparent" />
        <div className="relative av-container py-14 lg:py-20 space-y-4 text-av-linen">
          <div className="[&_*]:!text-av-linen/80"><Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Categories", to: "/categories" }, { label: category.name }]} /></div>
          <h1 data-testid="category-title" className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">{category.name}</h1>
          <p className="max-w-xl text-lg text-av-linen/80">{category.blurb}</p>
        </div>
      </section>
      <DiscoveryLayout key={slug} baseCategory={slug} empty="Vendors will list items in this category soon." />
    </div>
  );
}
