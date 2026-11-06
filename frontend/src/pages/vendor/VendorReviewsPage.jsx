import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RatingSummary, ReviewItem } from "@/components/trust/Reviews";
import { api, getErrorMessage } from "@/lib/api";

const Respond = ({ r, reload }) => {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState(r.my_response?.body || "");
  const save = async () => {
    try {
      const res = await api.put(`/vendor/reviews/${r.kind}/${r.id}/response`, { body });
      toast.success(res.data.response.status === "published" ? "Response published" : "Response is being checked before it appears");
      setOpen(false);
      reload();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  if (r.my_response?.status === "removed") return <p className="text-xs text-av-clay">Your response was removed by AfroVending.</p>;
  return open ? (
    <div className="space-y-2" data-testid={`respond-form-${r.id}`}>
      <Textarea maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} data-testid={`respond-input-${r.id}`} />
      <div className="flex gap-2"><Button size="sm" disabled={body.trim().length < 2} onClick={save} data-testid={`respond-submit-${r.id}`}>Post response</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </div>
  ) : <div className="flex items-center gap-2 text-xs">{r.my_response && r.my_response.status !== "published" && <span data-testid={`respond-status-${r.id}`}>Response being checked</span>}
    <Button size="sm" variant="outline" className="h-7" onClick={() => setOpen(true)} data-testid={`respond-open-${r.id}`}>{r.my_response ? "Edit response" : "Respond publicly"}</Button></div>;
};

export default function VendorReviewsPage() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/vendor/reviews").then((r) => setD(r.data)).catch((e) => toast.error(getErrorMessage(e))), []);
  useEffect(() => {
    load();
  }, [load]);
  if (!d) return null;
  const List = ({ rows, testId }) => (rows.length === 0 ? <p className="text-sm text-av-muted" data-testid={`${testId}-empty`}>Nothing here yet.</p> :
    <ul className="divide-y divide-av-line" data-testid={testId}>{rows.map((r) => <div key={r.id}><ReviewItem r={r} />{r.kind === "product" && <p className="-mt-2 mb-2 text-xs text-av-muted">{r.product_title}</p>}<Respond r={r} reload={load} /></div>)}</ul>);
  return (
    <div className="av-container space-y-8 py-8" data-testid="vendor-reviews-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Reviews & ratings</h1>
      <p className="text-sm text-av-muted">You can post one public response per review and report reviews that break the rules. You can't edit or remove customer reviews.</p>
      <div className="grid gap-5 md:grid-cols-2">
        <section className="rounded-2xl border border-av-line bg-white p-5"><p className="av-eyebrow mb-2">Product reviews</p><RatingSummary s={d.summary} empty="No reviews yet." testId="vendor-product-rating" /></section>
        <section className="rounded-2xl border border-av-line bg-white p-5"><p className="av-eyebrow mb-2">Seller service</p><RatingSummary s={d.summary.seller} empty="No seller ratings yet." testId="vendor-seller-rating" /></section>
      </div>
      <section className="rounded-2xl border border-av-line bg-white p-5"><h2 className="font-semibold">Product reviews</h2><List rows={d.product} testId="vendor-product-reviews" /></section>
      <section className="rounded-2xl border border-av-line bg-white p-5"><h2 className="font-semibold">Seller service reviews</h2><List rows={d.seller} testId="vendor-seller-reviews" /></section>
    </div>
  );
}
