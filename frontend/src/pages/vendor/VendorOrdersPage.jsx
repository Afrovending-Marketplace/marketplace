import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const TABS = ["", "pending", "accepted", "partially_shipped", "shipped", "ready_for_pickup", "delivered", "cancelled"];
const label = (s) => (s ? s.replace(/_/g, " ") : "all");
const act = async (fn, msg, after) => {
  try {
    await fn();
    toast.success(msg);
    after();
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};

const Ship = ({ vo, reload }) => {
  const [qty, setQty] = useState({});
  const [carrier, setCarrier] = useState("usps");
  const [tn, setTn] = useState("");
  const lines = Object.entries(qty).filter(([, q]) => Number(q) > 0).map(([order_item_id, q]) => ({ order_item_id, quantity: Number(q) }));
  return (
    <div className="space-y-2 rounded-xl bg-av-sand p-3 text-xs" data-testid={`vo-ship-form-${vo.order_number}`}>
      {vo.items.map((i) => <label key={i.id} className="flex items-center gap-2">{i.title} — {i.quantity - i.shipped_qty - i.cancelled_qty} to ship
        <Input className="h-8 w-16 bg-white" value={qty[i.id] || ""} onChange={(e) => setQty({ ...qty, [i.id]: e.target.value })} data-testid={`vo-ship-qty-${i.sku}`} /></label>)}
      <div className="flex flex-wrap gap-2">
        <select className="h-8 rounded border border-av-line bg-white px-2" value={carrier} onChange={(e) => setCarrier(e.target.value)} data-testid="vo-ship-carrier">
          {["usps", "ups", "fedex", "dhl", "other"].map((c) => <option key={c} value={c}>{c.toUpperCase()}</option>)}</select>
        <Input className="h-8 w-56 bg-white" placeholder="Tracking number" value={tn} onChange={(e) => setTn(e.target.value)} data-testid="vo-ship-tracking" />
        <Button size="sm" disabled={!lines.length || tn.length < 4} onClick={() => act(() => api.post(`/vendor/orders/${vo.id}/shipments`, { lines, carrier, tracking_number: tn }), "Shipment saved", reload)} data-testid="vo-ship-submit">Save shipment</Button>
      </div>
    </div>
  );
};

const Request = ({ r, reload }) => (
  <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={`vo-request-${r.id}`}>
    <b>{r.type} request</b> · {r.status}{r.rma_number && ` · ${r.rma_number}`} · “{r.reason}”{r.escalated && <StatusBadge tone="danger">overdue</StatusBadge>}
    {r.status === "requested" && <>
      <Button size="sm" onClick={() => act(() => api.post(`/vendor/requests/${r.id}/decide`, { decision: "approve" }), "Approved", reload)} data-testid={`vo-request-approve-${r.id}`}>Approve</Button>
      <Button size="sm" variant="outline" onClick={() => act(() => api.post(`/vendor/requests/${r.id}/decide`, { decision: "reject", note: "Declined by seller" }), "Rejected", reload)} data-testid={`vo-request-reject-${r.id}`}>Reject</Button></>}
    {r.status === "approved" && r.type === "return" && <Button size="sm" onClick={() => act(() => api.post(`/vendor/requests/${r.id}/receive`, { restock: true }), "Received and refunded", reload)} data-testid={`vo-request-receive-${r.id}`}>Mark received + restock + refund</Button>}
  </div>
);

const Order = ({ vo, reload }) => {
  const [ship, setShip] = useState(false);
  const status = (to) => act(() => api.post(`/vendor/orders/${vo.id}/status`, { to }), `Marked ${label(to)}`, reload);
  const a = vo.shipping_address;
  return (
    <li className="space-y-2 py-4 text-sm" data-testid={`vo-${vo.order_number}`}>
      <div className="flex flex-wrap items-center gap-2"><b>{vo.order_number}</b><StatusBadge tone={vo.status === "pending" ? "gold" : "neutral"}>{label(vo.status)}</StatusBadge>
        <span className="text-xs text-av-muted">{vo.fulfillment_type === "pickup" ? "Local pickup" : `${a.full_name}, ${a.line1}, ${a.city} ${a.postal_code} ${a.country}`}</span></div>
      <p className="text-xs">{vo.items.map((i) => `${i.title} × ${i.quantity} (${i.shipped_qty} shipped)`).join(" · ")} · {formatPrice(vo.charged_minor)}</p>
      {vo.shipments.map((s) => <div key={s.id} className="flex flex-wrap items-center gap-2 text-xs">{s.carrier_name} {s.tracking_number} · {label(s.status)}
        {s.status !== "delivered" && ["in_transit", "out_for_delivery", "delivered"].map((st) => <Button key={st} size="sm" variant="ghost" onClick={() => act(() => api.post(`/vendor/shipments/${s.id}/status`, { status: st }), "Updated", reload)} data-testid={`vo-shipment-${st}-${s.id}`}>{label(st)}</Button>)}</div>)}
      {vo.requests.map((r) => <Request key={r.id} r={r} reload={reload} />)}
      <div className="flex flex-wrap gap-2">
        {vo.status === "pending" && <Button size="sm" onClick={() => status("accepted")} data-testid={`vo-accept-${vo.order_number}`}>Accept</Button>}
        {vo.status === "accepted" && <Button size="sm" variant="outline" onClick={() => status("processing")} data-testid={`vo-processing-${vo.order_number}`}>Mark processing</Button>}
        {["accepted", "processing", "partially_shipped"].includes(vo.status) && vo.fulfillment_type === "ship" && <Button size="sm" variant="outline" onClick={() => setShip(!ship)} data-testid={`vo-ship-toggle-${vo.order_number}`}>Add shipment</Button>}
        {["accepted", "processing"].includes(vo.status) && vo.fulfillment_type === "pickup" && <Button size="sm" variant="outline" onClick={() => status("ready_for_pickup")} data-testid={`vo-ready-${vo.order_number}`}>Ready for pickup</Button>}
        {vo.status === "ready_for_pickup" && <Button size="sm" onClick={() => status("delivered")} data-testid={`vo-picked-up-${vo.order_number}`}>Picked up</Button>}
      </div>
      {ship && <Ship vo={vo} reload={() => { setShip(false); reload(); }} />}
    </li>
  );
};

const Methods = () => {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ type: "ship" });
  const load = useCallback(() => api.get("/vendor/shipping-methods").then((r) => setRows(r.data.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  const save = () => act(() => api.post("/vendor/shipping-methods", { name: f.name, type: f.type, amount_minor: Math.round(Number(f.amount || 0) * 100), eta: f.eta || "", pickup_address: f.pickup || "" }), "Shipping option added", () => { setF({ type: "ship" }); load(); });
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-shipping-methods">
      <h2 className="text-xl font-semibold">Your shipping & pickup options</h2>
      <ul className="text-sm">{rows.map((m) => <li key={m.id}>{m.name} · {m.type === "pickup" ? `pickup at ${m.pickup_address}` : formatPrice(m.amount_minor)} · {m.status}</li>)}</ul>
      <div className="flex flex-wrap gap-2">
        <select className="h-9 rounded border border-av-line bg-white px-2 text-sm" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} data-testid="method-type"><option value="ship">Delivery</option><option value="pickup">Local pickup</option></select>
        <Input className="h-9 w-40" placeholder="Name" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="method-name" />
        {f.type === "ship" ? <Input className="h-9 w-28" placeholder="Fee ($)" value={f.amount || ""} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="method-amount" />
          : <Input className="h-9 w-64" placeholder="Pickup address" value={f.pickup || ""} onChange={(e) => setF({ ...f, pickup: e.target.value })} data-testid="method-pickup" />}
        <Button size="sm" onClick={save} disabled={!f.name} data-testid="method-save">Add</Button>
      </div>
    </section>
  );
};

export default function VendorOrdersPage() {
  const [tab, setTab] = useState("");
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/vendor/orders", { params: tab ? { status: tab } : {} }).then((r) => setD(r.data)), [tab]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <div data-testid="vendor-orders-page" className="av-container max-w-6xl space-y-6 py-12">
      <div><p className="av-eyebrow">Vendor dashboard</p><h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">Orders</h1></div>
      <div className="flex gap-2 overflow-x-auto">{TABS.map((t) => <Button key={t || "all"} size="sm" variant={tab === t ? "default" : "outline"} onClick={() => setTab(t)} className="shrink-0" data-testid={`vo-tab-${t || "all"}`}>
        {label(t)}{t && d?.counts?.[t] ? ` (${d.counts[t]})` : ""}</Button>)}</div>
      <section className="rounded-2xl border border-av-line bg-white px-5">
        {d && d.data.length === 0 && <p className="py-6 text-sm text-av-muted" data-testid="vo-empty">No orders here.</p>}
        <ul className="divide-y divide-av-line">{d?.data.map((vo) => <Order key={vo.id} vo={vo} reload={load} />)}</ul>
      </section>
      <Methods />
    </div>
  );
}
