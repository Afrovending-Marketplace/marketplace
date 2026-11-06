import { useParams } from "react-router-dom";
import { Breadcrumbs } from "@/components/common/Breadcrumbs";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { ProductGallery } from "@/components/product/ProductGallery";
import { PurchasePanel } from "@/components/product/PurchasePanel";
import { ProductInfoTabs } from "@/components/product/ProductInfoTabs";
import { ProductRail } from "@/components/commerce/ProductRail";
import { ProductReviews } from "@/components/trust/PublicReviews";
import { getCategory, getProduct, getRelatedProducts, getVendor } from "@/lib/catalog";
import NotFoundPage from "@/pages/NotFoundPage";
import { useEffect } from "react";
import { Seo, productJsonLd } from "@/components/common/Seo";
import { WishlistButton } from "@/pages/account/MarketingPages";
import { track } from "@/lib/analytics";

const ProductMeta = ({ product }) => {
  useEffect(() => {
    track("product_view", { product_slug: product.slug });
  }, [product.slug]);
  const url = `${window.location.origin}/products/${product.slug}`;
  const img = product.images?.[0]?.src || product.images?.[0];
  return <Seo title={product.title} description={(product.description || product.title).slice(0, 160)} path={`/products/${product.slug}`} type="product"
    image={typeof img === "string" ? img : undefined} jsonLd={productJsonLd({ ...product, image: typeof img === "string" ? img : undefined }, url)} />;
};

export default function ProductPage() {
  const { slug } = useParams();
  const product = getProduct(slug);
  if (!product) return <NotFoundPage />;
  const vendor = getVendor(product.vendor_slug);
  const category = getCategory(product.category_slug);
  return (
    <div data-testid="product-page" key={slug}>
      <ProductMeta product={product} />
      <div className="av-container space-y-6 py-8 lg:py-12">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: category.name, to: `/categories/${category.slug}` }, { label: product.title }]} />
        <DevDataNotice />
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <ProductGallery images={product.images} title={product.title} />
          <div className="space-y-10">
            <PurchasePanel product={product} vendor={vendor} />
            <WishlistButton slug={slug} />
            <ProductInfoTabs product={product} />
          </div>
        </div>
        <ProductReviews slug={slug} />
      </div>
      <ProductRail testId="pdp-related" eyebrow="Keep exploring" title="You may also like" products={getRelatedProducts(product)} viewAll={`/categories/${category.slug}`} />
    </div>
  );
}
