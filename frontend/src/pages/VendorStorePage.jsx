import { Link, useParams } from "react-router-dom";
import { MapPin, ShieldCheck } from "lucide-react";
import { Breadcrumbs } from "@/components/common/Breadcrumbs";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { getCategory, getProductsByVendor, getVendor, isDevData } from "@/lib/catalog";
import NotFoundPage from "@/pages/NotFoundPage";
import { SellerRatings } from "@/components/trust/PublicReviews";

export default function VendorStorePage() {
  const { slug } = useParams();
  const vendor = getVendor(slug);
  if (!vendor) return <NotFoundPage />;
  const products = getProductsByVendor(slug);
  return (
    <div data-testid={`vendor-store-${slug}`}>
      <div className="relative h-48 sm:h-64 lg:h-72 overflow-hidden bg-av-indigo">
        <img src={vendor.banner} alt="" className="h-full w-full object-cover opacity-80" />
      </div>
      <div className="av-container">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end">
          <img src={vendor.logo} alt={`${vendor.name} logo`} className="relative z-10 -mt-14 h-28 w-28 rounded-2xl border-4 border-av-linen object-cover shadow-lg" />
          <div className="space-y-2 pb-1">
            <h1 data-testid="vendor-store-name" className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-av-ink">{vendor.name}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-av-muted">
              <span className="flex items-center gap-1"><MapPin className="h-4 w-4" />{vendor.location}</span>
              {vendor.verified && <StatusBadge tone="success"><ShieldCheck className="h-3 w-3" /> {isDevData() ? "Verified (sample)" : "Verified"}</StatusBadge>}
            </div>
          </div>
        </div>
        <div className="mt-6"><Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Vendors", to: "/vendors" }, { label: vendor.name }]} /></div>
        <div className="grid gap-10 py-10 lg:grid-cols-[280px_1fr] lg:py-14">
          <aside className="space-y-6">
            <DevDataNotice />
            <SellerRatings slug={slug} compact />
            <div>
              <p className="av-eyebrow mb-2">Our story</p>
              <p data-testid="vendor-store-story" className="text-sm leading-relaxed text-av-ink/80">{vendor.story}</p>
            </div>
            <div>
              <p className="av-eyebrow mb-2">Sells in</p>
              <div className="flex flex-wrap gap-2">
                {vendor.categories.map((c) => (
                  <Link key={c} to={`/categories/${c}`} data-testid={`vendor-store-category-${c}`} className="rounded-full border border-av-line bg-white px-3 py-1 text-xs hover:border-av-ink/40">{getCategory(c).name}</Link>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-av-line bg-white p-4 text-xs text-av-muted">Shipping, returns and contact policies for this store: [to be provided by vendor].</div>
          </aside>
          <section aria-labelledby="vendor-products-title" className="min-w-0">
            <h2 id="vendor-products-title" className="mb-6 text-2xl font-semibold text-av-ink">Products ({products.length})</h2>
            <ProductGrid products={products} testId="vendor-store-products" />
          </section>
        </div>
      </div>
    </div>
  );
}
