import { Link } from "react-router-dom";
import { SlidersHorizontal } from "lucide-react";
import { getCategories } from "@/lib/catalog";
import { cn } from "@/lib/utils";

export const FilterSidebar = ({ activeSlug, subcategories = [] }) => (
  <aside aria-label="Filters" data-testid="listing-filter-sidebar" className="space-y-8">
    <div>
      <p className="av-eyebrow mb-3">Categories</p>
      <ul className="space-y-1">
        {getCategories().map((c) => (
          <li key={c.slug}>
            <Link to={`/categories/${c.slug}`} data-testid={`filter-category-${c.slug}`} aria-current={c.slug === activeSlug ? "page" : undefined}
              className={cn("block rounded-lg px-3 py-1.5 text-sm transition-colors hover:bg-av-sand", c.slug === activeSlug ? "bg-av-sand font-semibold text-av-ink" : "text-av-muted")}>
              {c.name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
    {subcategories.length > 0 && (
      <div>
        <p className="av-eyebrow mb-3">Subcategories (sample)</p>
        <div className="flex flex-wrap gap-2">
          {subcategories.map((s) => (
            <span key={s} className="rounded-full border border-av-line bg-white px-3 py-1 text-xs text-av-ink/75">{s}</span>
          ))}
        </div>
      </div>
    )}
    <div className="rounded-xl border border-dashed border-av-line p-4 text-xs text-av-muted">
      <SlidersHorizontal className="mb-2 h-4 w-4" />
      Price, vendor, location and rating filters arrive with search &amp; discovery (Phase 05).
    </div>
  </aside>
);
