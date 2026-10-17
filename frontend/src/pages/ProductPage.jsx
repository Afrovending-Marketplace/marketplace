import { useParams } from "react-router-dom";
import { Breadcrumbs } from "@/components/common/Breadcrumbs";
import { DevDataNotice } from "@/components/common/DevDataNotice";
import { ProductGallery } from "@/components/product/ProductGallery";
import { PurchasePanel } from "@/components/product/PurchasePanel";
import { ProductInfoTabs } from "@/components/product/ProductInfoTabs";
import { ProductRail } from "@/components/commerce/ProductRail";
import { getCategory, getProduct, getRelatedProducts, getVendor } from "@/lib/catalog";
import NotFoundPage from "@/pages/NotFoundPage";

export default function ProductPage() {
  const { slug } = useParams();
  const product = getProduct(slug);
  if (!product) return <NotFoundPage />;
  const vendor = getVendor(product.vendor_slug);
  const category = getCategory(product.category_slug);
  return (
    <div data-testid="product-page" key={slug}>
      <div className="av-container space-y-6 py-8 lg:py-12">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: category.name, to: `/categories/${category.slug}` }, { label: product.title }]} />
        <DevDataNotice />
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <ProductGallery images={product.images} title={product.title} />
          <div className="space-y-10">
            <PurchasePanel product={product} vendor={vendor} />
            <ProductInfoTabs product={product} />
          </div>
        </div>
      </div>
      <ProductRail testId="pdp-related" eyebrow="Keep exploring" title="You may also like" products={getRelatedProducts(product)} viewAll={`/categories/${category.slug}`} />
    </div>
  );
}
