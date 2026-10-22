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
  return (
    <section className="flex flex-wrap items-end gap-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="admin-fulfillment-config">
      <label>Return window (days)<Input className="h-9 w-28" value={c.return_window_days} onChange={(e) => setC({ ...c, return_window_days: e.target.value })} data-testid="cfg-return-days" /></label>
      <label>Vendor response (hours)<Input className="h-9 w-28" value={c.response_hours} onChange={(e) => setC({ ...c, response_hours: e.target.value })} data-testid="cfg-response-hours" /></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={c.escalate_to_admin} onChange={(e) => setC({ ...c, escalate_to_admin: e.target.checked })} data-testid="cfg-escalate" /> Escalate overdue requests to admins</label>
      <Button size="sm" onClick={() => act(() => api.put("/admin/fulfillment/config", { ...c, return_window_days: Number(c.return_window_days), response_hours: Number(c.response_hours) }), "Saved")} data-testid="cfg-save">Save</Button>
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
      <section className="rounded-2xl border border-av-line bg-white px-5">
        {rows?.length === 0 && <p className="py-6 text-sm text-av-muted">No requests.</p>}
        <ul className="divide-y divide-av-line">{rows?.map((r) => <Req key={r.id} r={r} reload={load} />)}</ul>
      </section>
    </div>
  );
}
