import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";

const act = async (fn, msg, after) => {
  try {
    await fn();
    toast.success(msg);
    after?.();
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};

const Config = () => {
  const [c, setC] = useState(null);
  useEffect(() => {
    api.get("/admin/fulfillment/config").then((r) => setC(r.data));
  }, []);
  if (!c) return null;
  const num = (k, lbl) => <label className="flex flex-col">{lbl}<Input className="h-9 w-28" type="number" value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} data-testid={`cfg-${k}`} /></label>;
  const box = (k, lbl) => <label className="flex items-center gap-2"><input type="checkbox" checked={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.checked })} data-testid={`cfg-${k}`} /> {lbl}</label>;
  const NUMS = ["return_window_days", "response_hours", "default_handling_days", "min_handling_days", "max_handling_days", "reminder_hours_before", "admin_escalation_hours"];
  const payload = () => ({ ...c, ...Object.fromEntries(NUMS.map((k) => [k, Number(c[k])])), non_business_days: String(c.non_business_days_text ?? c.non_business_days.join(", ")).split(/[\s,]+/).filter(Boolean) });
  return (
    <section className="flex flex-wrap items-end gap-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="admin-fulfillment-config">
      <label>Return window (days)<Input className="h-9 w-28" value={c.return_window_days} onChange={(e) => setC({ ...c, return_window_days: e.target.value })} data-testid="cfg-return-days" /></label>
      <label>Vendor response (hours)<Input className="h-9 w-28" value={c.response_hours} onChange={(e) => setC({ ...c, response_hours: e.target.value })} data-testid="cfg-response-hours" /></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={c.escalate_to_admin} onChange={(e) => setC({ ...c, escalate_to_admin: e.target.checked })} data-testid="cfg-escalate" /> Escalate overdue requests to admins</label>
      <Button size="sm" onClick={() => act(async () => setC((await api.put("/admin/fulfillment/config", payload())).data), "Saved")} data-testid="cfg-save">Save</Button>
      <div className="flex w-full flex-wrap items-end gap-3 border-t border-av-line pt-3">
        <b className="w-full">Handling times & delay alerts</b>
        {num("default_handling_days", "Default (business days)")}{num("min_handling_days", "Minimum")}{num("max_handling_days", "Maximum")}
        {num("reminder_hours_before", "Vendor reminder (hours before)")}{num("admin_escalation_hours", "Escalate after overdue (hours)")}
        <label className="flex flex-col">Non-business days (YYYY-MM-DD, comma separated)<Input className="h-9 w-80" value={c.non_business_days_text ?? c.non_business_days.join(", ")} onChange={(e) => setC({ ...c, non_business_days_text: e.target.value })} data-testid="cfg-non_business_days" /></label>
        {box("vendor_reminder", "Remind vendors")}{box("customer_overdue_email", "Email customers when overdue")}{box("vendor_overdue_email", "Email vendors when overdue")}{box("escalate_overdue_to_admin", "Escalate to admins")}
      </div>
    </section>
  );
};

const Req = ({ r, reload }) => {
  const [note, setNote] = useState("");
  const decide = (decision) => act(() => api.post(`/admin/fulfillment/requests/${r.id}/decide`, { decision, note }), `Override: ${decision}`, reload);
  return (
    <li className="space-y-2 py-3 text-sm" data-testid={`admin-request-${r.id}`}>
      <p><b>{r.order_number}</b> · {r.vendor_name} · {r.type} · <StatusBadge tone={r.escalated ? "danger" : "neutral"}>{r.escalated ? `${r.status} · overdue` : r.status}</StatusBadge> · “{r.reason}”{r.rma_number && ` · ${r.rma_number}`}</p>
      <p className="text-xs text-av-muted">{r.history.map((h) => `${h.role}: ${h.status}${h.note ? ` (${h.note})` : ""}`).join(" → ")}</p>
      {["requested", "approved"].includes(r.status) && <div className="flex flex-wrap gap-2">
        <Input className="h-8 w-64" placeholder="Reason for override (required)" value={note} onChange={(e) => setNote(e.target.value)} data-testid={`admin-request-note-${r.id}`} />
        {r.status === "requested" && <Button size="sm" disabled={note.length < 3} onClick={() => decide("approve")} data-testid={`admin-request-approve-${r.id}`}>Approve</Button>}
        <Button size="sm" variant="outline" disabled={note.length < 3} onClick={() => decide("reject")} data-testid={`admin-request-reject-${r.id}`}>Reject</Button>
        {r.status === "approved" && r.type === "return" && <Button size="sm" variant="outline" onClick={() => act(() => api.post(`/admin/fulfillment/requests/${r.id}/receive`, { restock: true }), "Received & refunded", reload)} data-testid={`admin-request-receive-${r.id}`}>Mark received + refund</Button>}
      </div>}
    </li>
  );
};

const Overdue = () => {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({});
  const load = useCallback(() => api.get("/admin/fulfillment/overdue").then((r) => setRows(r.data.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <section className="rounded-2xl border border-av-line bg-white p-5" data-testid="admin-overdue">
      <h2 className="text-xl font-semibold">Overdue orders</h2>
      {rows?.length === 0 && <p className="py-3 text-sm text-av-muted" data-testid="admin-overdue-empty">Nothing overdue.</p>}
      <ul className="divide-y divide-av-line text-sm">{rows?.map((v) => (
        <li key={v.id} className="flex flex-wrap items-center gap-2 py-3" data-testid={`admin-overdue-${v.id}`}>
          <b>{v.order_number}</b> · {v.vendor_name} · {v.handling.kind === "pickup" ? "pickup preparation" : "shipment"} due {new Date(v.handling.deadline_at).toLocaleString()} · {v.status}
          <Input className="h-8 w-20" type="number" min="1" placeholder="Days" value={f[v.id]?.days || ""} onChange={(e) => setF({ ...f, [v.id]: { ...f[v.id], days: e.target.value } })} data-testid={`extend-days-${v.id}`} />
          <Input className="h-8 w-64" placeholder="Reason (required)" value={f[v.id]?.reason || ""} onChange={(e) => setF({ ...f, [v.id]: { ...f[v.id], reason: e.target.value } })} data-testid={`extend-reason-${v.id}`} />
          <Button size="sm" disabled={!f[v.id]?.days || (f[v.id]?.reason || "").length < 5} onClick={() => act(() => api.post(`/admin/fulfillment/vendor-orders/${v.id}/extend`, { business_days: Number(f[v.id].days), reason: f[v.id].reason }), "Deadline extended", load)} data-testid={`extend-submit-${v.id}`}>Extend</Button>
        </li>))}</ul>
    </section>
  );
};

export default function AdminFulfillmentPage() {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get("/admin/fulfillment/requests").then((r) => setRows(r.data.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <div data-testid="admin-fulfillment-page" className="av-container max-w-5xl space-y-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Cancellations & returns</h1>
      <Config />
      <Overdue />
      <section className="rounded-2xl border border-av-line bg-white px-5">
        {rows?.length === 0 && <p className="py-6 text-sm text-av-muted">No requests.</p>}
        <ul className="divide-y divide-av-line">{rows?.map((r) => <Req key={r.id} r={r} reload={load} />)}</ul>
      </section>
    </div>
  );
}
