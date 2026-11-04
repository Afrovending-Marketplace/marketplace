import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const CATS = ["order_issue", "delivery", "refund", "payment", "product", "account", "other"];
const STATUSES = ["open", "in_progress", "waiting_for_customer", "resolved", "closed"];
const lbl = (s) => s.replace(/_/g, " ");
const run = async (fn, msg, after) => {
  try {
    const r = await fn();
    toast.success(msg);
    after?.(r);
  } catch (e) {
    toast.error(getErrorMessage(e));
  }
};

const Thread = ({ t, staff }) => (
  <ul className="space-y-2" data-testid="ticket-thread">{t.messages.map((m, i) => (
    <li key={i} className={`rounded-xl p-3 text-sm ${m.internal ? "border border-dashed border-av-gold bg-white" : m.role === "customer" ? "bg-av-sand" : "bg-white border border-av-line"}`}>
      <p className="text-xs text-av-muted">{m.author}{m.internal && " · internal note"} · {new Date(m.at).toLocaleString()}</p>
      <p className="whitespace-pre-wrap">{m.body}</p></li>))}
    {staff && t.history?.length > 0 && <li className="text-xs text-av-muted">{t.history.map((h) => h.change).join(" → ")}</li>}</ul>
);

export function SupportPage() {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({ category: "order_issue" });
  const load = useCallback(() => api.get("/support/tickets").then((r) => setRows(r.data.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <div className="space-y-5" data-testid="support-page">
      <h1 className="text-3xl font-bold text-av-ink">Help & support</h1>
      <section className="space-y-2 rounded-2xl border border-av-line bg-white p-5" data-testid="ticket-form">
        <div className="flex flex-wrap gap-2"><select className="h-10 rounded border border-av-line px-2 text-sm" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="ticket-category">{CATS.map((c) => <option key={c} value={c}>{lbl(c)}</option>)}</select>
          <Input className="w-48" placeholder="Order number (optional)" value={f.order_number || ""} onChange={(e) => setF({ ...f, order_number: e.target.value })} data-testid="ticket-order" /></div>
        <Input placeholder="Subject" value={f.subject || ""} onChange={(e) => setF({ ...f, subject: e.target.value })} data-testid="ticket-subject" />
        <Textarea rows={4} placeholder="Tell us what happened" value={f.body || ""} onChange={(e) => setF({ ...f, body: e.target.value })} data-testid="ticket-body" />
        <Button onClick={() => run(() => api.post("/support/tickets", { ...f, order_number: f.order_number || null }), "Ticket created", () => { setF({ category: "order_issue" }); load(); })} data-testid="ticket-submit">Send</Button>
      </section>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white px-5 text-sm">{rows?.map((t) => <li key={t.id} className="flex justify-between py-3" data-testid={`my-ticket-${t.reference}`}>
        <Link className="underline" to={`/account/support/${t.id}`}>{t.reference} · {t.subject}</Link><StatusBadge tone="neutral">{lbl(t.status)}</StatusBadge></li>)}
        {rows?.length === 0 && <li className="py-3 text-av-muted">No tickets yet.</li>}</ul>
    </div>
  );
}

export function SupportTicketPage() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [body, setBody] = useState("");
  useEffect(() => {
    api.get(`/support/tickets/${id}`).then((r) => setT(r.data));
  }, [id]);
  if (!t) return null;
  return (
    <div className="space-y-4" data-testid="ticket-page">
      <h1 className="text-2xl font-bold">{t.reference} · {t.subject}</h1><StatusBadge tone="neutral" testId="ticket-status">{lbl(t.status)}</StatusBadge>
      <Thread t={t} />
      {t.status !== "closed" && <div className="space-y-2"><Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} data-testid="ticket-reply" />
        <Button disabled={!body.trim()} onClick={() => run(() => api.post(`/support/tickets/${id}/replies`, { body }), "Reply sent", (r) => { setT(r.data); setBody(""); })} data-testid="ticket-reply-send">Reply</Button></div>}
    </div>
  );
}

export default function AdminTicketsPage() {
  const [filters, setFilters] = useState({});
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const [reply, setReply] = useState({ body: "", internal: false });
  const load = useCallback(() => api.get("/admin/support/tickets", { params: filters }).then((r) => setRows(r.data.data)), [filters]);
  useEffect(() => {
    load();
  }, [load]);
  const sel = (k, opts) => <select className="h-9 rounded border border-av-line px-2 text-xs" value={filters[k] || ""} onChange={(e) => setFilters({ ...filters, [k]: e.target.value || undefined })} data-testid={`tf-${k}`}>
    <option value="">{k}: all</option>{opts.map((o) => <option key={o} value={o}>{lbl(o)}</option>)}</select>;
  const patch = (b) => run(() => api.patch(`/admin/support/tickets/${open.id}`, b), "Updated", (r) => { setOpen(r.data); load(); });
  return (
    <div className="av-container max-w-6xl space-y-5 py-12" data-testid="admin-tickets">
      <h1 className="text-3xl font-bold text-av-ink">Support tickets</h1>
      <div className="flex flex-wrap gap-2">{sel("status", STATUSES)}{sel("category", CATS)}{sel("priority", ["low", "normal", "high", "urgent"])}{sel("queue", ["support", "marketplace", "finance"])}
        <input type="date" className="h-9 rounded border border-av-line px-1 text-xs" onChange={(e) => setFilters({ ...filters, created_from: e.target.value || undefined })} data-testid="tf-from" /></div>
      <div className="grid gap-5 lg:grid-cols-2">
        <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white px-4 text-sm">{rows?.map((t) => <li key={t.id}><button type="button" className="w-full py-2 text-left" onClick={() => setOpen(t)} data-testid={`at-${t.reference}`}>
          <b>{t.reference}</b> · {t.subject} <span className="text-xs text-av-muted">· {lbl(t.status)} · {t.priority} · {t.queue}{t.assigned_name ? ` · ${t.assigned_name}` : ""}</span></button></li>)}</ul>
        {open && <section className="space-y-3 rounded-2xl border border-av-line bg-white p-4" data-testid="admin-ticket-detail">
          <h2 className="font-semibold">{open.reference} · {open.subject}</h2><p className="text-xs text-av-muted">{open.customer_email}{open.order_number && ` · order ${open.order_number}`}</p>
          <div className="flex flex-wrap gap-2 text-xs">
            <select className="h-8 rounded border px-1" value={open.status} onChange={(e) => patch({ status: e.target.value })} data-testid="at-status">{STATUSES.map((s) => <option key={s} value={s}>{lbl(s)}</option>)}</select>
            <select className="h-8 rounded border px-1" value={open.priority} onChange={(e) => patch({ priority: e.target.value })} data-testid="at-priority">{["low", "normal", "high", "urgent"].map((s) => <option key={s}>{s}</option>)}</select>
            <select className="h-8 rounded border px-1" value={open.queue} onChange={(e) => patch({ queue: e.target.value, note: "escalated" })} data-testid="at-queue">{["support", "marketplace", "finance"].map((s) => <option key={s}>{s}</option>)}</select>
            <Button size="sm" variant="outline" onClick={() => api.get("/auth/me").then((r) => patch({ assigned_to: r.data.user.id }))} data-testid="at-assign-me">Assign to me</Button></div>
          <p className="text-xs text-av-muted">Changing status never issues refunds or cancels orders — use the Payments or Orders tools for that.</p>
          <Thread t={open} staff />
          <Textarea rows={3} value={reply.body} onChange={(e) => setReply({ ...reply, body: e.target.value })} data-testid="at-reply" />
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={reply.internal} onChange={(e) => setReply({ ...reply, internal: e.target.checked })} data-testid="at-internal" />Internal note (customer won't see it)</label>
          <Button disabled={!reply.body.trim()} onClick={() => run(() => api.post(`/admin/support/tickets/${open.id}/replies`, reply), "Sent", (r) => { setOpen(r.data); setReply({ body: "", internal: false }); load(); })} data-testid="at-reply-send">Send</Button>
        </section>}
      </div>
    </div>
  );
}
