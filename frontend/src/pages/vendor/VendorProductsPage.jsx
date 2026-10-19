import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileUp, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { fileUrl } from "@/components/vendor/FileUpload";
import { STATUS_LABEL, STATUS_TONE, priceRange } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

const FILTERS = ["", "draft", "pending_review", "active", "rejected", "archived"];

const Row = ({ p }) => (
  <li className="flex flex-wrap items-center gap-4 p-4" data-testid={`vendor-product-row-${p.sku}`}>
    <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-av-sand">{p.thumb_url && <img src={fileUrl(p.thumb_url)} alt="" className="h-full w-full object-cover" />}</div>
    <div className="min-w-0 flex-1">
      <Link to={`/vendor/products/${p.id}`} className="font-semibold text-av-ink hover:underline" data-testid={`vendor-product-link-${p.sku}`}>{p.title}</Link>
      <p className="text-xs text-av-muted">{p.sku} · {p.variant_count} variant{p.variant_count === 1 ? "" : "s"} · {priceRange(p)}</p>
      {p.status === "rejected" && p.moderation_note && <p className="mt-1 text-xs text-red-700">Reviewer: {p.moderation_note}</p>}
    </div>
    <span className="text-sm" data-testid={`vendor-product-stock-${p.sku}`}>{p.stock_total} in stock</span>
    <StatusBadge tone={STATUS_TONE[p.status]} testId={`vendor-product-status-${p.sku}`}>{STATUS_LABEL[p.status]}</StatusBadge>
  </li>
);

const AlertPreference = ({ value, onSaved }) => {
  const save = async (v) => {
    try {
      await api.put("/vendor/preferences", { low_stock_alerts: v });
      onSaved(v);
      toast.success(v === "weekly" ? "You'll get one low-stock summary every Monday" : "You'll get an email as soon as an item runs low");
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-av-line bg-white p-4 text-sm" data-testid="low-stock-preference">
      <span className="font-medium text-av-ink">Low-stock emails</span>
      <Select value={value} onValueChange={save}>
        <SelectTrigger className="h-9 w-64 bg-white" data-testid="low-stock-preference-select"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="instant" data-testid="low-stock-preference-instant">One email per item, right away</SelectItem>
          <SelectItem value="weekly" data-testid="low-stock-preference-weekly">Weekly summary (Mondays)</SelectItem>
        </SelectContent>
      </Select>
      <span className="text-xs text-av-muted">The alert banner above always shows current low stock.</span>
    </div>
  );
};

export default function VendorProductsPage() {
  const [filter, setFilter] = useState("");
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    setData((await api.get("/vendor/products", { params: filter ? { status: filter } : {} })).data);
  }, [filter]);
  useEffect(() => {
    load();
  }, [load]);
  if (!data) return null;
  const total = Object.values(data.counts).reduce((a, b) => a + b, 0);
  const suspended = data.vendor_status !== "active";
  return (
    <div data-testid="vendor-products-page" className="av-container max-w-5xl space-y-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="av-eyebrow"><Link to="/vendor/dashboard" className="hover:underline">Vendor dashboard</Link></p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">Products</h1></div>
        {!suspended && <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" data-testid="vendor-import-link"><Link to="/vendor/products/import"><FileUp /> Import CSV</Link></Button>
          <Button asChild data-testid="vendor-new-product-link"><Link to="/vendor/products/new"><Plus /> New product</Link></Button>
        </div>}
      </div>
      {suspended && <StatusAlert tone="error" title="Vendor account suspended" testId="vendor-products-suspended">Catalog changes are disabled and your products are hidden from the storefront.</StatusAlert>}
      {data.low_stock.length > 0 && (
        <StatusAlert tone="warning" title={`Low stock on ${data.low_stock.length} product${data.low_stock.length === 1 ? "" : "s"}`} testId="vendor-low-stock-alert">
          {data.low_stock.map((p) => `${p.title} (${p.low_stock_variants.join(", ")})`).join(" · ")}
        </StatusAlert>
      )}
      {!suspended && <AlertPreference value={data.low_stock_alerts} onSaved={(v) => setData({ ...data, low_stock_alerts: v })} />}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter by status">
        {FILTERS.map((s) => (
          <button key={s || "all"} type="button" role="tab" aria-selected={filter === s} onClick={() => setFilter(s)} data-testid={`vendor-products-filter-${s || "all"}`}
            className={cn("rounded-full border px-4 py-1.5 text-sm transition-colors", filter === s ? "border-av-ink bg-av-ink text-av-linen" : "border-av-line bg-white hover:border-av-ink/40")}>
            {s ? STATUS_LABEL[s] : "All"} ({s ? data.counts[s] || 0 : total})
          </button>
        ))}
      </div>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white" data-testid="vendor-product-list">
        {data.data.length === 0 && <li className="p-8 text-center text-sm text-av-muted" data-testid="vendor-products-empty">No products here yet. Create one or import a CSV.</li>}
        {data.data.map((p) => <Row key={p.id} p={p} />)}
      </ul>
    </div>
  );
}
