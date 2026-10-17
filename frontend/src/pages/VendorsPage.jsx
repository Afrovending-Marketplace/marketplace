import { PageHero } from "@/components/common/PageHero";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { VendorCard } from "@/components/commerce/VendorCard";
import { getVendors } from "@/lib/catalog";

export default function VendorsPage() {
  return (
    <div data-testid="vendors-page">
      <PageHero eyebrow="Meet the makers" title="Vendors" crumbs={[{ label: "Home", to: "/" }, { label: "Vendors" }]}
        description="Independent businesses from the continent, the Caribbean and the diaspora." />
      <div className="av-container py-12 lg:py-16 space-y-8">
        <DevDataNotice />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {getVendors().map((v) => <VendorCard key={v.slug} vendor={v} />)}
        </div>
      </div>
    </div>
  );
}
