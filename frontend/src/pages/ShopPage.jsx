import { PageHero } from "@/components/common/PageHero";
import { ListingLayout } from "@/components/commerce/ListingLayout";
import { getProducts } from "@/lib/catalog";

export default function ShopPage() {
  return (
    <div data-testid="shop-page">
      <PageHero eyebrow="Marketplace" title="Shop all" crumbs={[{ label: "Home", to: "/" }, { label: "Shop all" }]}
        description="Everything on AfroVending, from every vendor and category." />
      <ListingLayout products={getProducts()} />
    </div>
  );
}
