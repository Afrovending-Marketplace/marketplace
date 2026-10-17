import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { SectionHeading } from "@/components/common/SectionHeading";
import { HOME } from "@/constants/testIds";
import { cn } from "@/lib/utils";

// Placeholder collection names; the real taxonomy is defined in Phase 03.
const COLLECTIONS = [
  { name: "Fashion & Textiles", image: "/images/textiles.jpg", span: "md:col-span-5 md:row-span-2" },
  { name: "Home & Ceramics", image: "/images/pottery.jpg", span: "md:col-span-7" },
  { name: "Spices & Teas", image: "/images/spices.jpg", span: "md:col-span-4" },
  { name: "Baskets & Woven Decor", image: "/images/baskets.jpg", span: "md:col-span-3" },
];

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

export const CategoryTeaser = () => (
  <section data-testid={HOME.categoryTeaser} className="av-container py-20 lg:py-28">
    <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
      <SectionHeading eyebrow="Collections" title="Curated cultural collections"
        description="A preview of the departments we're building. Full catalog browsing opens with the product catalog phase." />
    </div>
    <div className="mt-12 grid gap-4 md:grid-cols-12 md:auto-rows-[220px]">
      {COLLECTIONS.map((c, i) => (
        <Link key={c.name} to="/categories" data-testid={`home-collection-${slug(c.name)}`}
          className={cn("group relative overflow-hidden rounded-2xl min-h-[220px] av-rise", c.span)}
          style={{ animationDelay: `${i * 80}ms` }}>
          <img src={c.image} alt={c.name} loading="lazy"
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
          <div className="absolute inset-0 bg-gradient-to-t from-av-ink/80 via-av-ink/10 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between p-5">
            <h3 className="font-serif text-xl sm:text-2xl text-av-linen">{c.name}</h3>
            <span className="rounded-full bg-av-linen/90 p-2 text-av-ink transition-transform duration-300 group-hover:rotate-45">
              <ArrowUpRight className="h-4 w-4" />
            </span>
          </div>
        </Link>
      ))}
    </div>
  </section>
);
