import { Link } from "react-router-dom";
import { DevBadge } from "@/components/common/DevDataNotice";
import { formatPrice, getVendor } from "@/lib/catalog";

export const ProductCard = ({ product }) => {
  const vendor = getVendor(product.vendor_slug);
  return (
    <article data-testid={`product-card-${product.slug}`} className="group relative flex flex-col">
      <Link to={`/products/${product.slug}`} data-testid={`product-card-link-${product.slug}`}
        className="relative block overflow-hidden rounded-2xl bg-av-sand aspect-[4/5]">
        <img src={product.images[0]} alt={product.title} loading="lazy"
          className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
        {product.is_dev_data && <DevBadge className="absolute left-3 top-3" />}
      </Link>
      <div className="mt-3 space-y-1">
        <Link to={`/vendors/${vendor?.slug}`} data-testid={`product-card-vendor-${product.slug}`}
          className="text-xs font-medium uppercase tracking-wider text-av-muted hover:text-av-clay">{vendor?.name}</Link>
        <h3 className="font-sans text-base font-semibold leading-snug text-av-ink">
          <Link to={`/products/${product.slug}`} className="hover:underline underline-offset-4">{product.title}</Link>
        </h3>
        <p data-testid={`product-card-price-${product.slug}`} className="text-sm font-semibold text-av-ink">{product.price_max_minor > product.price_minor ? "From " : ""}{formatPrice(product.price_minor, product.currency)}</p>
      </div>
    </article>
  );
};

export const ProductGrid = ({ products, testId = "product-grid" }) => (
  <div data-testid={testId} className="grid grid-cols-2 gap-x-4 gap-y-10 sm:gap-x-6 lg:grid-cols-4">
    {products.map((p) => <ProductCard key={p.slug} product={p} />)}
  </div>
);
