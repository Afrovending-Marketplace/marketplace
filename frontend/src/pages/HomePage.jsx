import { HeroSection } from "@/components/home/HeroSection";
import { ShopByCategory, TrendingCategories } from "@/components/home/CategorySections";
import { FeaturedVendors } from "@/components/home/FeaturedVendors";
import { HowItWorks } from "@/components/home/HowItWorks";
import { VendorCta } from "@/components/home/VendorCta";
import { ProductRail } from "@/components/commerce/ProductRail";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { getFeaturedProducts, getNewArrivals } from "@/lib/catalog";
import { HOME } from "@/constants/testIds";

export default function HomePage() {
  return (
    <div data-testid={HOME.page}>
      <HeroSection />
      <div className="av-container"><DevDataNotice /></div>
      <ShopByCategory />
      <ProductRail testId="home-featured-products" eyebrow="Featured" title="Featured products"
        products={getFeaturedProducts().slice(0, 8)} viewAll="/shop" className="pt-4 lg:pt-8" />
      <TrendingCategories />
      <ProductRail testId="home-new-arrivals" eyebrow="Just in" title="New arrivals" products={getNewArrivals(4)} viewAll="/shop?sort=newest" />
      <FeaturedVendors />
      <HowItWorks />
      <VendorCta />
    </div>
  );
}
