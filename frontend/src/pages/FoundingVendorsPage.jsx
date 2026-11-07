import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { Seo } from "@/components/common/Seo";
import { FoundingBadge } from "@/components/commerce/FoundingBadge";
import { fileUrl } from "@/components/vendor/FileUpload";
import { api } from "@/lib/api";

const StoreCard = ({ s }) => (
  <Link to={`/store/${s.slug}`} data-testid={`founding-store-${s.slug}`}
    className="group block overflow-hidden rounded-2xl border border-av-line bg-white transition-shadow duration-300 hover:shadow-xl">
    <div className="h-28 overflow-hidden bg-av-sand">
      {s.banner_url && <img src={fileUrl(s.banner_url)} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />}
    </div>
    <div className="px-5 pb-6">
      <div className="-mt-8 h-16 w-16 overflow-hidden rounded-full border-4 border-white bg-white shadow">
        <img src={s.logo_url ? fileUrl(s.logo_url) : "/brand/logo-mark.png"} alt={`${s.display_name} logo`} loading="lazy" className="h-full w-full object-cover" />
      </div>
      <h3 className="mt-3 text-lg font-semibold text-av-ink">{s.display_name}</h3>
      {s.location && <p className="mt-1 flex items-center gap-1 text-xs text-av-muted"><MapPin className="h-3.5 w-3.5" />{s.location}</p>}
      {s.tagline && <p className="mt-3 line-clamp-2 text-sm text-av-ink/75">{s.tagline}</p>}
      <FoundingBadge className="mt-4" testId={`founding-store-badge-${s.slug}`} />
    </div>
  </Link>
);

export default function FoundingVendorsPage() {
  const [stores, setStores] = useState(null);
  useEffect(() => {
    api.get("/founding-vendors").then((r) => setStores(r.data.data)).catch(() => setStores([]));
  }, []);
  return (
    <div data-testid="founding-vendors-page">
      <Seo title="Meet our Founding Vendors" description="The first independent businesses to open their stores on AfroVending." />
      <PageHero eyebrow="The first to open their doors" title="Meet our Founding Vendors" crumbs={[{ label: "Home", to: "/" }, { label: "Vendors", to: "/vendors" }, { label: "Founding Vendors" }]}
        description="These businesses were approved before AfroVending's launch or in its first 30 days. The badge recognises them as founders; it does not affect prices, fees or search ranking." />
      <div className="av-container py-12 lg:py-16">
        {stores === null ? null : stores.length ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4" data-testid="founding-vendors-grid">{stores.map((s) => <StoreCard key={s.slug} s={s} />)}</div>
        ) : (
          <div className="space-y-3 rounded-2xl border border-dashed border-av-line bg-white p-10 text-center" data-testid="founding-vendors-empty">
            <FoundingBadge testId="founding-empty-badge" />
            <p className="text-lg font-semibold text-av-ink">Founding spots are open.</p>
            <p className="text-sm text-av-muted">Vendors approved before launch or in the first 30 days after it earn the Founding Vendor badge for good.</p>
            <Link to="/sell" data-testid="founding-empty-sell-link" className="inline-block font-semibold text-av-clay hover:underline">Apply to become a Founding Vendor</Link>
          </div>
        )}
      </div>
    </div>
  );
}
