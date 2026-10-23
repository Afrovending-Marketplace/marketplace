import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const TABS = ["", "pending", "accepted", "partially_shipped", "shipped", "ready_for_pickup", "delivered", "cancelled"];
import { BulkSlips } from "@/components/vendor/BulkSlips";
import { PickupHoursEditor, emptyHours } from "@/components/vendor/PickupHoursEditor";
import { PickupHours } from "@/components/common/PickupHours";

const label = (s) => (s ? s.replace(/_/g, " ") : "all");
const day = (d) => new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const openSlip = async (vo, shipment, print) => {
  try {
    const r = await api.get(`/vendor/orders/${vo.id}/packing-slip`, { params: shipment ? { shipment_id: shipment.id } : {}, responseType: "blob" });
    const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
    if (print) {
      const frame = document.createElement("iframe");
      frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
      frame.src = url;
      frame.onload = () => {
        frame.contentWindow.focus();
        frame.contentWindow.print();
        setTimeout(() => { frame.remove(); URL.revokeObjectURL(url); }, 60000);
      };
      document.body.appendChild(frame);
      return;
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = `packing-slip-${vo.order_number}${shipment ? `-${shipment.tracking_number}` : ""}.pdf`.replace(/\s/g, "");
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};
const SlipButtons = ({ vo, shipment, tid }) => (
  <span className="inline-flex gap-1">
    <Button size="sm" variant="ghost" onClick={() => openSlip(vo, shipment, false)} data-testid={`slip-download-${tid}`}>{shipment ? "Slip for this package" : "Download packing slip"}</Button>
    <Button size="sm" variant="ghost" onClick={() => openSlip(vo, shipment, true)} data-testid={`slip-print-${tid}`}>Print</Button>
  </span>
);
const Deadline = ({ vo }) => {
  const h = vo.handling;
  if (!h || !["accepted", "processing", "partially_shipped"].includes(vo.status)) return null;
  const late = new Date(h.deadline_at) < new Date();
  return <span className={`text-xs ${late ? "font-semibold text-av-clay" : "text-av-muted"}`} data-testid={`vo-deadline-${vo.order_number}`}>
    {h.kind === "pickup" ? "Ready for pickup by" : "Ship by"} {day(h.deadline_at)}{late ? " — overdue" : ""}{h.extensions?.length ? " (extended)" : ""}</span>;
};
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

const Request = ({ r, vo, reload }) => (
  <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={`vo-request-${r.id}`}>
    <b>{r.type} request</b> · {r.status}{r.rma_number && ` · ${r.rma_number}`} · “{r.reason}”{r.escalated && <StatusBadge tone="danger">overdue</StatusBadge>}
    {r.status === "requested" && r.type === "cancel" && !["accepted", "processing"].includes(vo.status) && <span className="text-av-muted">Already shipped — can't be cancelled; reject it.</span>}
    {r.status === "requested" && <>
      {(r.type === "return" || ["accepted", "processing"].includes(vo.status)) && <Button size="sm" onClick={() => act(() => api.post(`/vendor/requests/${r.id}/decide`, { decision: "approve" }), "Approved", reload)} data-testid={`vo-request-approve-${r.id}`}>Approve</Button>}
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
      <div className="flex flex-wrap items-center gap-2"><b>{vo.order_number}</b><StatusBadge tone={vo.status === "pending" ? "gold" : "neutral"}>{label(vo.status)}</StatusBadge><Deadline vo={vo} />
        <span className="text-xs text-av-muted">{vo.fulfillment_type === "pickup" ? "Local pickup" : `${a.full_name}, ${a.line1}, ${a.city} ${a.postal_code} ${a.country}`}</span></div>
      <p className="text-xs">{vo.items.map((i) => `${i.title} × ${i.quantity} (${vo.fulfillment_type === "pickup" ? (vo.status === "delivered" ? `${i.shipped_qty} collected` : vo.status === "ready_for_pickup" ? `${i.shipped_qty} waiting for collection` : "not ready yet") : `${i.shipped_qty} shipped`})`).join(" · ")} · {formatPrice(vo.charged_minor)}</p>
      {vo.shipments.map((s) => <div key={s.id} className="flex flex-wrap items-center gap-2 text-xs">{s.carrier_name} {s.tracking_number} · {label(s.status)}<SlipButtons vo={vo} shipment={s} tid={s.id} />
        {s.status !== "delivered" && ["in_transit", "out_for_delivery", "delivered"].filter((st) => s.status === "exception" || ["label_created", "in_transit", "out_for_delivery", "delivered"].indexOf(st) > ["label_created", "in_transit", "out_for_delivery", "delivered"].indexOf(s.status)).map((st) => <Button key={st} size="sm" variant="ghost" onClick={() => act(() => api.post(`/vendor/shipments/${s.id}/status`, { status: st }), "Updated", reload)} data-testid={`vo-shipment-${st}-${s.id}`}>{label(st)}</Button>)}</div>)}
      {vo.requests.map((r) => <Request key={r.id} r={r} vo={vo} reload={reload} />)}
      <div className="flex flex-wrap gap-2">
        {vo.status === "pending" && <Button size="sm" onClick={() => status("accepted")} data-testid={`vo-accept-${vo.order_number}`}>Accept</Button>}
        {vo.status === "accepted" && <Button size="sm" variant="outline" onClick={() => status("processing")} data-testid={`vo-processing-${vo.order_number}`}>Mark processing</Button>}
        {["accepted", "processing", "partially_shipped"].includes(vo.status) && vo.fulfillment_type === "ship" && <Button size="sm" variant="outline" onClick={() => setShip(!ship)} data-testid={`vo-ship-toggle-${vo.order_number}`}>Add shipment</Button>}
        {["accepted", "processing"].includes(vo.status) && vo.fulfillment_type === "pickup" && <Button size="sm" variant="outline" onClick={() => status("ready_for_pickup")} data-testid={`vo-ready-${vo.order_number}`}>Ready for pickup</Button>}
        {vo.status === "ready_for_pickup" && <Button size="sm" onClick={() => status("delivered")} data-testid={`vo-picked-up-${vo.order_number}`}>Picked up</Button>}
        {vo.status !== "cancelled" && <SlipButtons vo={vo} tid={vo.order_number} />}
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
  const [editing, setEditing] = useState(null);
  const save = () => act(() => api.post("/vendor/shipping-methods", { name: f.name, type: f.type, amount_minor: f.type === "pickup" ? 0 : Math.round(Number(f.amount || 0) * 100), eta: f.eta || "", pickup_address: f.pickup || "", handling_days: f.days === undefined || f.days === "" ? null : Number(f.days), pickup_hours: f.type === "pickup" ? (f.hours || emptyHours()) : null }), "Shipping option added", () => { setF({ type: "ship" }); load(); });
  const saveHours = () => act(() => api.put(`/vendor/shipping-methods/${editing.id}`, editing), "Pickup hours saved", () => { setEditing(null); load(); });
  const setDays = async (m, input) => {
    try {
      await api.put(`/vendor/shipping-methods/${m.id}`, { ...m, handling_days: Number(input.value) });
      toast.success("Handling time updated");
      load();
    } catch (err) {
      input.value = m.handling_days ?? 3;
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="vendor-shipping-methods">
      <h2 className="text-xl font-semibold">Your shipping & pickup options</h2>
      <ul className="space-y-1 text-sm">{rows.map((m) => <li key={m.id} className="flex flex-wrap items-center gap-2" data-testid={`method-row-${m.id}`}>{m.name} · {m.type === "pickup" ? `pickup at ${m.pickup_address}` : formatPrice(m.amount_minor)} · {m.status} ·
        <Input className="h-8 w-16" type="number" min="0" defaultValue={m.handling_days ?? 3} onBlur={(e) => Number(e.target.value) !== m.handling_days && setDays(m, e.target)} data-testid={`method-days-${m.id}`} /> business days to {m.type === "pickup" ? "prepare" : "ship"}
        {m.type === "pickup" && <Button size="sm" variant="ghost" onClick={() => setEditing({ ...m, pickup_hours: m.pickup_hours || emptyHours() })} data-testid={`method-hours-edit-${m.id}`}>{m.pickup_hours ? "Edit pickup hours" : "Set pickup hours"}</Button>}
        {m.type === "pickup" && editing?.id !== m.id && <PickupHours hours={m.pickup_hours} compact testId={`method-hours-${m.id}`} />}
        {editing?.id === m.id && <><PickupHoursEditor value={editing.pickup_hours} onChange={(v) => setEditing({ ...editing, pickup_hours: v })} />
          <Button size="sm" onClick={saveHours} data-testid="method-hours-save">Save hours</Button><Button size="sm" variant="ghost" onClick={() => setEditing(null)} data-testid="method-hours-cancel">Cancel</Button></>}</li>)}</ul>
      <div className="flex flex-wrap gap-2">
        <select className="h-9 rounded border border-av-line bg-white px-2 text-sm" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} data-testid="method-type"><option value="ship">Delivery</option><option value="pickup">Local pickup</option></select>
        <Input className="h-9 w-40" placeholder="Name" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="method-name" />
        {f.type === "ship" ? <Input className="h-9 w-28" placeholder="Fee ($)" value={f.amount || ""} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="method-amount" />
          : <Input className="h-9 w-64" placeholder="Pickup address" value={f.pickup || ""} onChange={(e) => setF({ ...f, pickup: e.target.value })} data-testid="method-pickup" />}
        <Input className="h-9 w-36" type="number" min="0" placeholder="Handling days (3)" value={f.days ?? ""} onChange={(e) => setF({ ...f, days: e.target.value })} data-testid="method-days" />
        <Button size="sm" onClick={save} disabled={!f.name} data-testid="method-save">Add</Button>
        {f.type === "pickup" && !editing && <PickupHoursEditor value={f.hours} onChange={(v) => setF({ ...f, hours: v })} />}
        {f.type === "pickup" && editing && <p className="text-xs text-av-muted">Finish editing the hours above first.</p>}
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
      <BulkSlips refreshKey={d} />
      <section className="rounded-2xl border border-av-line bg-white px-5">
        {d && d.data.length === 0 && <p className="py-6 text-sm text-av-muted" data-testid="vo-empty">No orders here.</p>}
        <ul className="divide-y divide-av-line">{d?.data.map((vo) => <Order key={vo.id} vo={vo} reload={load} />)}</ul>
      </section>
      <Methods />
    </div>
  );
}
