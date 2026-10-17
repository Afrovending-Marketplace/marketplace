import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { SectionHeading } from "@/components/common/SectionHeading";
import { VendorCard } from "@/components/commerce/VendorCard";
import { getFeaturedVendors } from "@/lib/catalog";

export const FeaturedVendors = () => (
  <section data-testid="home-featured-vendors" className="bg-av-sand/60 border-y border-av-line">
    <div className="av-container py-16 lg:py-24">
      <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading eyebrow="Meet the makers" title="Featured vendors" description="The people and studios behind the products." />
        <Link to="/vendors" data-testid="home-featured-vendors-view-all"
          className="inline-flex items-center gap-1 text-sm font-semibold text-av-clay hover:gap-2 transition-all">All vendors <ArrowRight className="h-4 w-4" /></Link>
      </div>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {getFeaturedVendors().map((v) => <VendorCard key={v.slug} vendor={v} />)}
      </div>
    </div>
  </section>
);
