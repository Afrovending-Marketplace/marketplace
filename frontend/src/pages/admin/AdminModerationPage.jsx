import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Stars } from "@/components/trust/Reviews";
import { api, getErrorMessage } from "@/lib/api";

const act = async (fn, ok, after) => {
  try {
    await fn();
    toast.success(ok);
    after();
  } catch (e) {
    toast.error(getErrorMessage(e));
  }
};

const Decide = ({ r, part, reload }) => {
  const [reason, setReason] = useState("");
  const go = (action) => act(() => api.post(`/admin/reviews/${r.kind}/${r.id}/decision`, { part, action, reason }), `Review ${action}d`, reload);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input className="h-8 max-w-xs" placeholder="Reason (required, shown to the author)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid={`mod-reason-${part}-${r.id}`} />
      {["approve", "reject", "remove"].map((a) => <Button key={a} size="sm" variant={a === "approve" ? "default" : "outline"} disabled={reason.trim().length < 5} onClick={() => go(a)} data-testid={`mod-${a}-${part}-${r.id}`}>{a}</Button>)}
    </div>
  );
};

const ReviewsQueue = () => {
  const [kind, setKind] = useState("product");
  const [rows, setRows] = useState([]);
  const load = useCallback(() => api.get("/admin/reviews", { params: { kind } }).then((r) => setRows(r.data.data)).catch((e) => toast.error(getErrorMessage(e))), [kind]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="mod-reviews">
      <div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">Reviews needing action</h2>
        {["product", "seller"].map((k) => <Button key={k} size="sm" variant={kind === k ? "default" : "outline"} onClick={() => setKind(k)} data-testid={`mod-kind-${k}`}>{k === "product" ? "Product reviews" : "Seller ratings"}</Button>)}</div>
      <p className="text-xs text-av-muted">Never reject a review just because it's negative. Decide only on documented policy violations.</p>
      {rows.length === 0 && <p className="text-sm text-av-muted" data-testid="mod-reviews-empty">Queue is clear.</p>}
      <ul className="divide-y divide-av-line">{rows.map((r) => <li key={r.id} className="space-y-2 py-3 text-sm" data-testid={`mod-review-${r.id}`}>
        <p className="text-xs text-av-muted">{r.order_number} · {r.kind === "seller" ? r.vendor_name : r.product_title} · status <b>{r.status}</b>{r.flags.length > 0 && ` · flags: ${r.flags.join(", ")}`}</p>
        <Stars value={r.rating} /><p className="font-semibold">{r.title}</p><p className="whitespace-pre-line">{r.comment}</p>
        {r.reports.length > 0 && <p className="text-xs text-av-clay" data-testid={`mod-reports-${r.id}`}>Reports: {r.reports.map((x) => `${x.part} · ${x.reason} (${x.reporter_role}, ${x.status})`).join("; ")}</p>}
        <Decide r={r} part="review" reload={load} />
        {r.response && <div className="ml-4 space-y-1 rounded-lg bg-av-sand p-2"><p className="text-xs">Vendor response · <b>{r.response.status}</b>{r.response.flags.length > 0 && ` · flags: ${r.response.flags.join(", ")}`}</p>
          <p>{r.response.body}</p><Decide r={r} part="response" reload={load} /></div>}</li>)}</ul>
    </section>
  );
};

const Messages = () => {
  const [rows, setRows] = useState(null);
  const [note, setNote] = useState({});
  const load = useCallback(() => api.get("/admin/messages/flagged").then((r) => setRows(r.data.data)).catch(() => setRows([])), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="mod-messages">
      <h2 className="font-semibold">Flagged order messages</h2>
      <p className="text-xs text-av-muted">Originals are shown only here, for moderation. Payment redirection and threats are held from the recipient until reviewed.</p>
      {rows && rows.length === 0 && <p className="text-sm text-av-muted" data-testid="mod-messages-empty">No flagged messages.</p>}
      <ul className="divide-y divide-av-line">{(rows || []).map((m) => <li key={m.id} className="space-y-1 py-3 text-sm" data-testid={`mod-message-${m.id}`}>
        <p className="text-xs text-av-muted">{m.order_number} · {m.vendor_name} · from {m.sender_role} {m.sender_name} · {m.flags.join(", ")}{m.held && " · HELD"}</p>
        <p><b>Original:</b> {m.original}</p><p className="text-av-muted"><b>Shown:</b> {m.shown}</p>
        <div className="flex flex-wrap gap-2"><Input className="h-8 max-w-xs" placeholder="Note (required)" value={note[m.id] || ""} onChange={(e) => setNote({ ...note, [m.id]: e.target.value })} data-testid={`mod-msg-note-${m.id}`} />
          {[["dismiss", "False positive"], ["confirm", "Confirm violation"], ["hide", "Hide message"]].map(([a, l]) => <Button key={a} size="sm" variant="outline" disabled={(note[m.id] || "").trim().length < 3}
            onClick={() => act(() => api.post(`/admin/messages/${m.id}/review`, { action: a, note: note[m.id] }), "Saved", load)} data-testid={`mod-msg-${a}-${m.id}`}>{l}</Button>)}</div></li>)}</ul>
    </section>
  );
};

const FIELDS = [["approved_domains", "Approved domains (never masked)"], ["payment_domains", "Payment link domains"], ["payment_terms", "Payment solicitation terms"],
  ["threat_terms", "Threat phrases"], ["abuse_terms", "Abusive words"], ["spam_terms", "Spam / promotion phrases"]];

const Rules = () => {
  const [r, setR] = useState(null);
  useEffect(() => {
    api.get("/admin/moderation/rules").then((x) => setR(Object.fromEntries(FIELDS.map(([k]) => [k, x.data[k].join(", ")])))).catch(() => setR(false));
  }, []);
  if (!r) return null;
  const save = () => act(() => api.put("/admin/moderation/rules", Object.fromEntries(FIELDS.map(([k]) => [k, r[k].split(",").map((s) => s.trim()).filter(Boolean)]))), "Rules saved", () => {});
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="mod-rules">
      <h2 className="font-semibold">Moderation rules</h2>
      {FIELDS.map(([k, l]) => <label key={k} className="block text-xs">{l}<Textarea className="mt-1 text-sm" value={r[k]} onChange={(e) => setR({ ...r, [k]: e.target.value })} data-testid={`mod-rule-${k}`} /></label>)}
      <Button size="sm" onClick={save} data-testid="mod-rules-save">Save rules</Button>
    </section>
  );
};

export default function AdminModerationPage() {
  const [s, setS] = useState(null);
  useEffect(() => {
    api.get("/admin/reviews/summary").then((r) => setS(r.data)).catch(() => setS(false));
  }, []);
  return (
    <div className="av-container space-y-6 py-8" data-testid="admin-moderation-page">
      <p className="text-sm"><Link to="/admin" className="underline">← Admin</Link></p>
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Reviews & message moderation</h1>
      {s && <div className="grid gap-3 sm:grid-cols-4 text-sm" data-testid="mod-summary">
        <div className="rounded-xl bg-white p-4"><p className="text-xs text-av-muted">Product reviews (published)</p><p className="text-2xl font-bold" data-testid="mod-sum-product">{s.product.total}{s.product.average != null && ` · ${s.product.average.toFixed(1)}★`}</p></div>
        <div className="rounded-xl bg-white p-4"><p className="text-xs text-av-muted">Seller ratings (published)</p><p className="text-2xl font-bold" data-testid="mod-sum-seller">{s.seller.total}{s.seller.average != null && ` · ${s.seller.average.toFixed(1)}★`}</p></div>
        <div className="rounded-xl bg-white p-4"><p className="text-xs text-av-muted">Waiting for moderation</p><p className="text-2xl font-bold" data-testid="mod-sum-pending">{s.product.by_status.pending_moderation + s.seller.by_status.pending_moderation}</p></div>
        <div className="rounded-xl bg-white p-4"><p className="text-xs text-av-muted">Open reports · flagged messages</p><p className="text-2xl font-bold" data-testid="mod-sum-reports">{s.open_reports} · {s.flagged_messages}</p></div></div>}
      {s !== false && <ReviewsQueue />}
      <Messages />
      {s !== false && <Rules />}
    </div>
  );
}
