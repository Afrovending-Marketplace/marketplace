import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { formatPrice, getCategory } from "@/lib/catalog";
import { cn } from "@/lib/utils";

const Group = ({ title, children }) => (
  <div className="space-y-3"><p className="av-eyebrow">{title}</p>{children}</div>
);

const CatLink = ({ c, active, onClick, child }) => (
  <button type="button" onClick={onClick} aria-pressed={active} data-testid={`filter-category-${c.slug}`}
    className={cn("flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-sm transition-colors hover:bg-av-sand", child && "pl-6", active ? "bg-av-sand font-semibold text-av-ink" : "text-av-muted")}>
    <span>{c.name}</span><span className="text-xs">{c.product_count}</span>
  </button>
);

const Categories = ({ facets, state, update, baseCategory }) => {
  const base = baseCategory ? getCategory(baseCategory) : null;
  const tree = facets?.categories || [];
  const counted = (slug) => tree.flatMap((c) => [c, ...(c.children || [])]).find((c) => c.slug === slug)?.product_count || 0;
  if (base) {
    const kids = (base.children || []).map((k) => ({ ...k, product_count: counted(k.slug) })).filter((k) => k.product_count || k.slug === state.category);
    if (!kids.length) return null;
    return (
      <Group title="Subcategories">
        <CatLink c={{ slug: base.slug, name: `All ${base.name}`, product_count: counted(base.slug) }} active={state.category === base.slug} onClick={() => update({ category: "" })} />
        {kids.map((k) => <CatLink key={k.slug} c={k} child active={state.category === k.slug} onClick={() => update({ category: k.slug })} />)}
      </Group>
    );
  }
  return (
    <Group title="Category">
      <CatLink c={{ slug: "all", name: "All categories", product_count: tree.reduce((s, c) => s + c.product_count, 0) }} active={!state.category} onClick={() => update({ category: "" })} />
      {tree.map((c) => {
        const open = state.category === c.slug || c.children?.some((k) => k.slug === state.category);
        return (
          <div key={c.slug}>
            <CatLink c={c} active={state.category === c.slug} onClick={() => update({ category: c.slug })} />
            {open && c.children.filter((k) => k.product_count).map((k) => <CatLink key={k.slug} c={k} child active={state.category === k.slug} onClick={() => update({ category: k.slug })} />)}
          </div>
        );
      })}
    </Group>
  );
};

const Price = ({ facets, state, update }) => {
  const [min, setMin] = useState(state.min);
  const [max, setMax] = useState(state.max);
  const range = facets?.price;
  return (
    <Group title="Price (USD)">
      <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); update({ min, max }); }}>
        <Input aria-label="Minimum price" inputMode="decimal" placeholder="Min" value={min} onChange={(e) => setMin(e.target.value.replace(/[^\d.]/g, ""))} className="h-9 bg-white" data-testid="filter-price-min" />
        <span className="text-av-muted">–</span>
        <Input aria-label="Maximum price" inputMode="decimal" placeholder="Max" value={max} onChange={(e) => setMax(e.target.value.replace(/[^\d.]/g, ""))} className="h-9 bg-white" data-testid="filter-price-max" />
        <Button type="submit" size="sm" variant="outline" data-testid="filter-price-apply">Go</Button>
      </form>
      {range?.min != null && <p className="text-xs text-av-muted" data-testid="filter-price-range">Prices here: {formatPrice(range.min)} – {formatPrice(range.max)}</p>}
    </Group>
  );
};

const Vendors = ({ facets, state, update }) => {
  const selected = state.vendor ? state.vendor.split(",") : [];
  const list = facets?.vendors || [];
  if (!list.length) return null;
  const toggle = (slug) => update({ vendor: (selected.includes(slug) ? selected.filter((s) => s !== slug) : [...selected, slug]).join(",") });
  return (
    <Group title="Vendor">
      {list.slice(0, 12).map((v) => (
        <label key={v.slug} className="flex cursor-pointer items-center gap-2 text-sm text-av-ink">
          <Checkbox checked={selected.includes(v.slug)} onCheckedChange={() => toggle(v.slug)} data-testid={`filter-vendor-${v.slug}`} />
          <span className="flex-1">{v.name}</span><span className="text-xs text-av-muted">{v.count}</span>
        </label>
      ))}
    </Group>
  );
};

export const FilterPanel = ({ facets, state, update, clear, activeCount, baseCategory }) => (
  <aside aria-label="Filters" data-testid="listing-filter-sidebar" className="space-y-8">
    <Categories facets={facets} state={state} update={update} baseCategory={baseCategory} />
    <Price key={`${state.min}-${state.max}`} facets={facets} state={state} update={update} />
    <Vendors facets={facets} state={state} update={update} />
    <Group title="Availability">
      <label className="flex cursor-pointer items-center gap-2 text-sm text-av-ink">
        <Checkbox checked={state.in_stock} onCheckedChange={(v) => update({ in_stock: !!v })} data-testid="filter-in-stock" />
        <span className="flex-1">In stock only</span><span className="text-xs text-av-muted">{facets?.in_stock ?? ""}</span>
      </label>
    </Group>
    {activeCount > 0 && <Button variant="ghost" size="sm" onClick={clear} data-testid="filter-clear-all">Clear all filters</Button>}
  </aside>
);
