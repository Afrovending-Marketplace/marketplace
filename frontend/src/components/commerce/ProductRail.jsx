import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { ProductGrid } from "@/components/commerce/ProductCard";
import { SectionHeading } from "@/components/common/SectionHeading";

export const ProductRail = ({ eyebrow, title, description, products, viewAll, testId, className = "" }) => (
  <section data-testid={testId} className={`av-container py-16 lg:py-24 ${className}`}>
    <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <SectionHeading eyebrow={eyebrow} title={title} description={description} />
      {viewAll && (
        <Link to={viewAll} data-testid={`${testId}-view-all`}
          className="inline-flex items-center gap-1 text-sm font-semibold text-av-clay hover:gap-2 transition-all">
          View all <ArrowRight className="h-4 w-4" />
        </Link>
      )}
    </div>
    <ProductGrid products={products} testId={`${testId}-grid`} />
  </section>
);
