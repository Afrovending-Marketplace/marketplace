import { HeroSection } from "@/components/home/HeroSection";
import { HomepageContent } from "@/pages/admin/AdminContentPage";
import { CampaignStrip } from "@/components/home/CampaignStrip";
import { ShopByCategory, TrendingCategories } from "@/components/home/CategorySections";
import { FeaturedVendors } from "@/components/home/FeaturedVendors";
import { HowItWorks } from "@/components/home/HowItWorks";
import { VendorCta } from "@/components/home/VendorCta";
import { ProductRail } from "@/components/commerce/ProductRail";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { getFeaturedProducts, getNewArrivals } from "@/lib/catalog";
import { HOME } from "@/constants/testIds";

export default function HomePage() {
  const featured = getFeaturedProducts().slice(0, 8);
  const fresh = getNewArrivals(4);
  return (
    <div data-testid={HOME.page}>
      <HeroSection />
      <CampaignStrip />
      <HomepageContent />
      <div className="av-container"><DevDataNotice /></div>
      <ShopByCategory />
      {featured.length > 0 && <ProductRail testId="home-featured-products" eyebrow="Featured" title="Featured products"
        products={featured} viewAll="/shop" className="pt-4 lg:pt-8" />}
      <TrendingCategories />
      {fresh.length > 0 && <ProductRail testId="home-new-arrivals" eyebrow="Just in" title="New arrivals" products={fresh} viewAll="/shop?sort=newest" />}
      <FeaturedVendors />
      <HowItWorks />
      <VendorCta />
    </div>
  );
}
