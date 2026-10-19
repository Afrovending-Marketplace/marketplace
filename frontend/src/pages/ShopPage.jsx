import { PageHero } from "@/components/common/PageHero";
import { DiscoveryLayout } from "@/components/discovery/DiscoveryLayout";

export default function ShopPage() {
  return (
    <div data-testid="shop-page">
      <PageHero eyebrow="Marketplace" title="Shop all" crumbs={[{ label: "Home", to: "/" }, { label: "Shop all" }]}
        description="Everything on AfroVending, from every vendor and category." />
      <DiscoveryLayout />
    </div>
  );
}
