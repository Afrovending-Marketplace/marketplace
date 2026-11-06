import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { MapPin, ShieldCheck } from "lucide-react";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { fileUrl } from "@/components/vendor/FileUpload";
import { api } from "@/lib/api";
import { normalizeProduct } from "@/lib/catalog";
import NotFoundPage from "@/pages/NotFoundPage";
import { SellerRatings } from "@/components/trust/PublicReviews";

export default function PublicStorePage() {
  const { slug } = useParams();
  const [store, setStore] = useState(undefined);
  const [products, setProducts] = useState([]);
  useEffect(() => {
    api.get(`/stores/${slug}`).then((r) => setStore(r.data)).catch(() => setStore(null));
    api.get("/catalog/products", { params: { vendor: slug, limit: 60 } }).then((r) => setProducts(r.data.data.map(normalizeProduct))).catch(() => setProducts([]));
  }, [slug]);
  if (store === undefined) return null;
  if (store === null) return <NotFoundPage />;
  return (
    <div data-testid="public-store-page">
      <div className="h-48 sm:h-64 bg-av-indigo">{store.banner_url && <img src={fileUrl(store.banner_url)} alt="" className="h-full w-full object-cover" />}</div>
      <div className="av-container pb-16">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end">
          <div className="relative z-10 -mt-14 h-28 w-28 overflow-hidden rounded-2xl border-4 border-av-linen bg-white shadow-lg">
            {store.logo_url && <img src={fileUrl(store.logo_url)} alt={`${store.display_name} logo`} className="h-full w-full object-cover" />}
          </div>
          <div className="space-y-2">
            <h1 data-testid="public-store-name" className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-av-ink">{store.display_name}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-av-muted">
              {store.location && <span className="flex items-center gap-1"><MapPin className="h-4 w-4" />{store.location}</span>}
              <StatusBadge tone="success"><ShieldCheck className="h-3 w-3" /> Approved vendor</StatusBadge>
            </div>
          </div>
        </div>
        {store.tagline && <p className="mt-6 text-lg text-av-ink">{store.tagline}</p>}
        <p className="mt-4 max-w-3xl whitespace-pre-line text-av-ink/80">{store.description}</p>
        <div className="mt-8 rounded-2xl border border-av-line bg-white p-5"><SellerRatings slug={slug} /></div>
        <section className="mt-12" aria-labelledby="store-products-title">
          <h2 id="store-products-title" className="mb-6 text-2xl font-semibold text-av-ink">Products ({products.length})</h2>
          {products.length ? <ProductGrid products={products} testId="public-store-products" />
            : <p data-testid="public-store-empty" className="rounded-2xl border border-dashed border-av-line p-8 text-center text-sm text-av-muted">This vendor hasn't published any products yet.</p>}
        </section>
      </div>
    </div>
  );
}
