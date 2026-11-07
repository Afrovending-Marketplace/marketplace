import { Link } from "react-router-dom";
import { PageHero } from "@/components/common/PageHero";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { VendorCard } from "@/components/commerce/VendorCard";
import { getVendors } from "@/lib/catalog";

export default function VendorsPage() {
  const vendors = getVendors();
  return (
    <div data-testid="vendors-page">
      <PageHero eyebrow="Meet the makers" title="Vendors" crumbs={[{ label: "Home", to: "/" }, { label: "Vendors" }]}
        description="Independent businesses from the continent, the Caribbean and the diaspora." />
      <div className="av-container py-12 lg:py-16 space-y-8">
        <DevDataNotice />
        <Link to="/founding-vendors" data-testid="vendors-founding-link" className="inline-flex items-center gap-2 text-sm font-semibold text-av-clay hover:underline">Meet our Founding Vendors →</Link>
        {vendors.length ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {vendors.map((v) => <VendorCard key={v.slug} vendor={v} />)}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-av-line bg-white p-10 text-center space-y-3" data-testid="vendors-empty-state">
            <p className="text-lg font-semibold text-av-ink">Our first vendors are getting ready.</p>
            <p className="text-sm text-av-muted">Approved stores will appear here as they open. Run a business? You could be one of the first.</p>
            <Link to="/sell" data-testid="vendors-empty-sell-link" className="inline-block font-semibold text-av-clay hover:underline">Apply to sell on AfroVending</Link>
          </div>
        )}
      </div>
    </div>
  );
}
