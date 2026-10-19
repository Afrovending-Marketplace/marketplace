import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/common/StatusBadge";
import { fileUrl } from "@/components/vendor/FileUpload";
import { STATUS_LABEL, STATUS_TONE, money, priceRange } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

const FILTERS = ["pending_review", "active", "rejected", "all"];

const Review = ({ id, onDone }) => {
  const [d, setD] = useState(null);
  const [note, setNote] = useState("");
  useEffect(() => {
    if (id) {
      setD(null); setNote("");
      api.get(`/admin/products/${id}`).then((r) => setD(r.data));
    }
  }, [id]);
  const decide = async (decision) => {
    try {
      await api.post(`/admin/products/${id}/moderate`, { decision, note });
      toast.success({ approve: "Product approved and live", reject: "Product rejected", take_down: "Product taken down" }[decision]);
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const p = d?.product;
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onDone()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto rounded-2xl bg-av-linen" data-testid="admin-product-dialog">
        <DialogHeader><DialogTitle className="font-serif text-2xl">{p?.title || "Product"}</DialogTitle>
          <DialogDescription>{d ? `${d.vendor_name} · ${p.sku} · ${p.category_slug}` : "Loading…"}</DialogDescription></DialogHeader>
        {p && (
          <div className="space-y-4 text-sm">
            <div className="flex gap-2 overflow-x-auto">{d.images.map((i) => <img key={i.id} src={fileUrl(i.thumb_url)} alt={i.alt} className="h-24 w-24 shrink-0 rounded-lg object-cover" />)}</div>
            <p className="whitespace-pre-line rounded-xl bg-white p-3">{p.description}</p>
            {p.tags.length > 0 && <p><b>Tags:</b> {p.tags.join(", ")}</p>}
            <ul className="rounded-xl border border-av-line bg-white">
              {d.variants.filter((v) => v.status === "active").map((v) => <li key={v.id} className="flex justify-between border-b border-av-line p-2 last:border-0"><span>{v.label} · {v.sku}</span><span>{money(v.price_minor)} · {v.quantity_on_hand} in stock</span></li>)}
            </ul>
            {["pending_review", "active"].includes(p.status) ? (
              <>
                <Textarea aria-label="Note to vendor" placeholder="Note to vendor (required to reject or take down)" value={note} onChange={(e) => setNote(e.target.value)} className="bg-white" data-testid="admin-product-note" />
                <div className="flex flex-wrap gap-2">
                  {p.status === "pending_review" ? (<>
                    <Button variant="indigo" onClick={() => decide("approve")} data-testid="admin-product-approve">Approve</Button>
                    <Button variant="destructive" onClick={() => decide("reject")} data-testid="admin-product-reject">Reject</Button>
                  </>) : <Button variant="destructive" onClick={() => decide("take_down")} data-testid="admin-product-takedown">Take down</Button>}
                </div>
              </>
            ) : <StatusBadge tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</StatusBadge>}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default function AdminProductsPage() {
  const [filter, setFilter] = useState("pending_review");
  const [data, setData] = useState({ data: [], counts: {} });
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    setData((await api.get("/admin/products", { params: { status: filter } })).data);
  }, [filter]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <div data-testid="admin-products-page" className="av-container space-y-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Product moderation</h1>
      <div className="flex flex-wrap gap-2" role="tablist">
        {FILTERS.map((s) => (
          <button key={s} type="button" role="tab" aria-selected={filter === s} onClick={() => setFilter(s)} data-testid={`admin-products-filter-${s}`}
            className={cn("rounded-full border px-4 py-1.5 text-sm transition-colors", filter === s ? "border-av-ink bg-av-ink text-av-linen" : "border-av-line bg-white hover:border-av-ink/40")}>
            {s === "all" ? "All" : STATUS_LABEL[s]} {s !== "all" && `(${data.counts[s] || 0})`}
          </button>
        ))}
      </div>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white" data-testid="admin-product-list">
        {data.data.length === 0 && <li className="p-8 text-center text-sm text-av-muted" data-testid="admin-products-empty">Nothing here.</li>}
        {data.data.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-4 p-4" data-testid={`admin-product-row-${p.sku}`}>
            <div className="h-12 w-12 overflow-hidden rounded-lg bg-av-sand">{p.thumb_url && <img src={fileUrl(p.thumb_url)} alt="" className="h-full w-full object-cover" />}</div>
            <div className="min-w-0 flex-1"><b>{p.title}</b><p className="text-xs text-av-muted">{p.vendor_name} · {p.sku} · {priceRange(p)}</p></div>
            <StatusBadge tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</StatusBadge>
            <Button size="sm" variant="outline" onClick={() => setOpen(p.id)} data-testid={`admin-product-review-${p.sku}`}>Review</Button>
          </li>
        ))}
      </ul>
      <Review id={open} onDone={() => { setOpen(null); load(); }} />
    </div>
  );
}
